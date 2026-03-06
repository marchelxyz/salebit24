"""Точка входа: FastAPI-приложение для приёма вебхуков CRM."""

import json
import logging
import os
import re
from typing import Any
from urllib.parse import parse_qs

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from uvicorn import run

from src.crm_notifier.bitrix24_client import (
    fetch_contact_and_convert,
    fetch_lead_and_convert,
    register_event_handlers,
)
from src.crm_notifier.bitrix24_models import (
    Bitrix24WebhookPayload,
    parse_bitrix24_payload_flexible,
)
from src.crm_notifier.models import ContactPayload
from src.crm_notifier.telegram_chat_store import set_chat_id
from src.crm_notifier.telegram_client import send_contact_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CRM → Telegram Notifier",
    description="Вебхук-сервис для уведомлений о новых контактах в Telegram",
    version="1.0.0",
)

SUPPORTED_BITRIX_EVENTS = {"ONCRMCONTACTADD", "ONCRMLEADADD"}


def _get_telegram_webhook_url() -> str | None:
    """URL для Telegram webhook (напр. https://xxx.railway.app/webhook/telegram)."""
    full = os.environ.get("TELEGRAM_WEBHOOK_URL")
    if full:
        return full
    bitrix = os.environ.get("BITRIX24_HANDLER_URL", "")
    base = (
        os.environ.get("TELEGRAM_WEBHOOK_BASE_URL")
        or os.environ.get("RAILWAY_STATIC_URL")
        or (bitrix.rstrip("/").replace("/webhook/bitrix24", "") if bitrix else "")
    )
    if base and not base.startswith("http"):
        base = "https://" + base
    return f"{base}/webhook/telegram" if base else None


def _unflatten_form(parsed: dict[str, list[str]]) -> dict[str, Any]:
    """Разворачивает data[FIELDS][ID]=123 в data: {FIELDS: {ID: 123}}."""
    result: dict[str, Any] = {}
    for key, val_list in parsed.items():
        val = val_list[0] if len(val_list) == 1 else val_list
        if "[" not in key:
            result[key] = val
            continue
        parts = key.replace("]", "").split("[")
        current = result
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = val
                break
            if part not in current:
                current[part] = {}
            current = current[part]
    return result


@app.on_event("startup")
def _register_telegram_webhook() -> None:
    """Регистрирует webhook Telegram при старте (если настроен URL)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    webhook_url = _get_telegram_webhook_url()
    if token and webhook_url:
        import httpx

        url = f"https://api.telegram.org/bot{token}/setWebhook"
        try:
            resp = httpx.post(url, json={"url": webhook_url}, timeout=10.0)
            if resp.is_success:
                logger.info("Telegram webhook зарегистрирован: %s", webhook_url)
            else:
                logger.warning("Telegram setWebhook failed: %s", resp.text)
        except Exception as e:
            logger.warning("Не удалось зарегистрировать Telegram webhook: %s", e)


@app.get("/")
def health_check() -> dict[str, str]:
    """Проверка работоспособности сервиса."""
    return {"status": "ok", "service": "crm-telegram-notifier"}


@app.get("/call/{phone}")
def redirect_to_callto(phone: str) -> RedirectResponse:
    """
    Редиректит на callto: с нормализованным номером для Mango Telecom.
    """
    normalized = _normalize_phone_digits(phone)
    if not normalized:
        raise HTTPException(status_code=400, detail="Неверный формат номера телефона")
    redirect_url = f"callto://+{normalized}"
    logger.info("Call redirect: phone=%s, redirect_url=%s", normalized, redirect_url)
    return RedirectResponse(url=redirect_url, status_code=302)


@app.post("/webhook/crm")
def handle_crm_webhook(payload: ContactPayload) -> dict[str, str]:
    """
    Принимает данные о новом контакте из CRM и отправляет в Telegram.

    Ожидаемый JSON: {"name": "...", "phone": "...", "title": "..."}
    """
    try:
        send_contact_notification(payload)
        logger.info("Уведомление отправлено: %s", payload.name)
        return {"status": "ok", "message": "Уведомление отправлено"}
    except ValueError as e:
        logger.error("Ошибка конфигурации: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка отправки в Telegram")
        raise HTTPException(status_code=500, detail="Ошибка отправки уведомления") from e


@app.post("/webhook/telegram")
async def handle_telegram_webhook(body: dict[str, Any] = Body(...)) -> dict[str, str]:
    """
    Webhook для обновлений Telegram. Сохраняет chat_id при /start.
    """
    message = body.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if text == "/start" and chat_id is not None:
        set_chat_id(chat_id)
        logger.info("Chat ID зарегистрирован: %s", chat_id)
    return {"status": "ok"}


@app.post("/webhook/bitrix24")
async def handle_bitrix24_webhook(request: Request) -> dict[str, str]:
    """
    Обработчик исходящих вебхуков Bitrix24.

    Принимает события OnCrmContactAdd и OnCrmLeadAdd.
    Подпишите на них локальное приложение — URL этого endpoint.
    """
    content_type = request.headers.get("content-type", "")
    raw_body = await request.body()
    body_preview = raw_body[:2000].decode("utf-8", errors="replace") if raw_body else "(empty)"
    if "access_token" in body_preview:
        body_preview = re.sub(r'"access_token"\s*:\s*"[^"]*"', '"access_token":"***"', body_preview)
    logger.info(
        "Bitrix24 webhook: content-type=%s, body_len=%d, body=%s",
        content_type,
        len(raw_body),
        body_preview,
    )

    body: dict
    if "application/json" in content_type:
        try:
            body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as e:
            logger.warning("Bitrix24 webhook: некорректный JSON: %s", e)
            raise HTTPException(status_code=400, detail="Невалидный JSON") from e
    elif "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(raw_body.decode("utf-8", errors="replace"))
        body = _unflatten_form(parsed)
        if "data" in body and isinstance(body["data"], str):
            try:
                body["data"] = json.loads(body["data"])
            except json.JSONDecodeError:
                pass
    else:
        logger.warning("Bitrix24 webhook: неожиданный content-type: %s", content_type)
        raise HTTPException(status_code=415, detail=f"Ожидается JSON или form-urlencoded, получен: {content_type}")

    event = (body.get("event") or body.get("EVENT") or "").upper()
    auth_raw = body.get("auth") or body.get("AUTH")
    if isinstance(auth_raw, dict):
        access_token = auth_raw.get("access_token") or auth_raw.get("ACCESS_TOKEN")
        client_endpoint = auth_raw.get("client_endpoint") or auth_raw.get("CLIENT_ENDPOINT")
    else:
        access_token = client_endpoint = None

    if event == "ONAPPINSTALL" and access_token and client_endpoint:
        handler_url = os.environ.get("BITRIX24_HANDLER_URL") or (
            str(request.base_url).rstrip("/") + "/webhook/bitrix24"
        )
        logger.info("Bitrix24 ONAPPINSTALL: регистрация event.bind, handler=%s", handler_url)
        try:
            register_event_handlers(client_endpoint, access_token, handler_url)
            logger.info("Bitrix24: OnCrmContactAdd и OnCrmLeadAdd зарегистрированы")
            return {"status": "ok", "message": "Event handlers registered"}
        except Exception as e:
            logger.exception("Bitrix24 ONAPPINSTALL: ошибка event.bind: %s", e)
            raise HTTPException(status_code=500, detail="Ошибка регистрации событий") from e

    try:
        payload = Bitrix24WebhookPayload.model_validate(body)
    except Exception as e:
        logger.warning("Bitrix24 webhook: ошибка валидации, пробуем гибкий парсер: %s", e)
        payload = parse_bitrix24_payload_flexible(body)
        if payload is None:
            logger.warning("Bitrix24 webhook: не удалось распарсить, body=%s", body)
            raise HTTPException(status_code=400, detail="Неверный формат payload") from e

    event = payload.event.upper()
    if event not in SUPPORTED_BITRIX_EVENTS:
        logger.info("Игнорируем событие: %s", event)
        return {"status": "ok", "message": f"Событие {event} не обрабатывается"}

    if not payload.auth:
        logger.error("Вебхук без auth — Bitrix24 не передал токены")
        raise HTTPException(
            status_code=500,
            detail="Токены авторизации не переданы. Создайте локальное приложение от имени пользователя.",
        ) from None

    try:
        if event == "ONCRMCONTACTADD":
            contact_payload = fetch_contact_and_convert(payload)
        else:
            contact_payload = fetch_lead_and_convert(payload)
        logger.info(
            "Bitrix24: entity_id=%s, name=%s, phone=%s, title=%s",
            payload.get_entity_id(),
            contact_payload.name,
            contact_payload.phone[:3] + "***" if len(contact_payload.phone) > 3 else contact_payload.phone,
            contact_payload.title,
        )
        send_contact_notification(contact_payload)
        logger.info("Уведомление отправлено: %s (событие %s)", contact_payload.name, event)
        return {"status": "ok", "message": "Уведомление отправлено"}
    except ValueError as e:
        logger.error("Ошибка Bitrix24: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка обработки вебхука Bitrix24")
        raise HTTPException(status_code=500, detail="Ошибка отправки уведомления") from e


def _main() -> None:
    """Запускает сервер."""
    port = int(os.environ.get("PORT", "8000"))
    run(app, host="0.0.0.0", port=port)


def _normalize_phone_digits(phone: str) -> str:
    """
    Нормализует номер телефона до формата 7XXXXXXXXXX.

    Args:
        phone: Номер телефона в любом распространенном формате.

    Returns:
        Номер в формате 7XXXXXXXXXX или пустая строка при некорректном входе.
    """
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        return "7" + digits[1:]
    if digits.startswith("9") and len(digits) == 10:
        return "7" + digits
    if digits.startswith("7") and len(digits) == 11:
        return digits
    return ""


if __name__ == "__main__":
    _main()
