"""Точка входа: FastAPI-приложение для приёма вебхуков CRM."""

import json
import logging
import os
import re
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from uvicorn import run

from src.crm_notifier.bitrix24_client import fetch_contact_and_convert, fetch_lead_and_convert
from src.crm_notifier.bitrix24_models import Bitrix24WebhookPayload
from src.crm_notifier.models import ContactPayload
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


@app.get("/")
def health_check() -> dict[str, str]:
    """Проверка работоспособности сервиса."""
    return {"status": "ok", "service": "crm-telegram-notifier"}


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
        body = {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}
        if "data" in body and isinstance(body["data"], str):
            try:
                body["data"] = json.loads(body["data"])
            except json.JSONDecodeError:
                pass
    else:
        logger.warning("Bitrix24 webhook: неожиданный content-type: %s", content_type)
        raise HTTPException(status_code=415, detail=f"Ожидается JSON или form-urlencoded, получен: {content_type}")

    try:
        payload = Bitrix24WebhookPayload.model_validate(body)
    except Exception as e:
        logger.warning("Bitrix24 webhook: ошибка валидации: %s, body=%s", e, body)
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


if __name__ == "__main__":
    _main()
