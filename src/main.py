"""Точка входа: FastAPI-приложение для приёма вебхуков CRM."""

import logging
import os

from fastapi import FastAPI, HTTPException
from uvicorn import run

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


def _main() -> None:
    """Запускает сервер."""
    port = int(os.environ.get("PORT", "8000"))
    run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    _main()
