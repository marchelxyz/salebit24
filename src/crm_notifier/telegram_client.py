"""Telegram Bot API client for sending messages."""

import os
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from src.crm_notifier.models import ContactPayload

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def _get_bot_token() -> str:
    """Возвращает токен бота из переменных окружения."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        msg = "TELEGRAM_BOT_TOKEN не задан в переменных окружения"
        raise ValueError(msg)
    return token


def _get_chat_id() -> str:
    """Возвращает ID чата для уведомлений."""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        msg = "TELEGRAM_CHAT_ID не задан в переменных окружения"
        raise ValueError(msg)
    return chat_id


def _normalize_phone(phone: str) -> str:
    """Приводит номер телефона к формату 7XXXXXXXXXX для Mango Office."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "7" + digits
    return digits


def _build_phone_link(phone: str) -> str:
    """Формирует кликабельную ссылку для номера телефона."""
    normalized = _normalize_phone(phone)
    template = os.environ.get("MANGO_CALL_URL_TEMPLATE")
    if template and "{phone}" in template:
        return template.replace("{phone}", normalized)
    return f"tel:+{normalized}"


def _escape_html(text: str) -> str:
    """Экранирует символы для HTML-режима Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_message(payload: "ContactPayload") -> str:
    """Формирует текст сообщения для Telegram в HTML."""
    lines = ["🆕 <b>Новый контакт в CRM</b>", ""]
    if payload.title:
        lines.append(f"<b>Название:</b> {_escape_html(payload.title)}")
    lines.append(f"<b>Имя:</b> {_escape_html(payload.name)}")
    phone_link = _build_phone_link(payload.phone)
    lines.append(f'<b>Телефон:</b> <a href="{phone_link}">{_escape_html(payload.phone)}</a>')
    return "\n".join(lines)


def send_contact_notification(payload: "ContactPayload") -> None:
    """
    Отправляет уведомление о новом контакте в Telegram.

    Args:
        payload: Данные контакта из CRM.
    """
    token = _get_bot_token()
    chat_id = _get_chat_id()
    text = _format_message(payload)
    url = f"{TELEGRAM_API_BASE}{token}/sendMessage"
    payload_data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload_data)
        response.raise_for_status()
