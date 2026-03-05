"""Клиент для запросов к REST API Bitrix24."""

import logging
from typing import Any

import httpx

from src.crm_notifier.bitrix24_models import (
    Bitrix24WebhookPayload,
    contact_to_payload,
    lead_to_payload,
)
from src.crm_notifier.models import ContactPayload

logger = logging.getLogger(__name__)


def _call_bitrix24_api(
    client_endpoint: str,
    method: str,
    access_token: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Вызывает метод REST API Bitrix24."""
    url = _build_api_url(client_endpoint, method)
    payload = {**params, "auth": access_token}
    with httpx.Client(timeout=15.0) as client:
        response = client.post(url, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = response.text
            logger.error("Bitrix24 %s: %s %s, body=%s", method, response.status_code, e, body)
            raise
        data = response.json()
    if "error" in data:
        raise ValueError(f"Bitrix24 API error: {data.get('error_description', data['error'])}")
    return data.get("result", {})


def _build_api_url(client_endpoint: str, method: str) -> str:
    """Формирует URL для вызова метода REST API."""
    base = client_endpoint.rstrip("/")
    return f"{base}/{method}"


def register_event_handlers(
    client_endpoint: str,
    access_token: str,
    handler_url: str,
) -> None:
    """
    Регистрирует обработчики OnCrmContactAdd и OnCrmLeadAdd через event.bind.

    Вызывается при ONAPPINSTALL — иначе Bitrix24 не будет отправлять события.
    """
    for event_name in ("ONCRMCONTACTADD", "ONCRMLEADADD"):
        _call_bitrix24_api(
            client_endpoint,
            "event.bind",
            access_token,
            {"event": event_name, "handler": handler_url},
        )


def fetch_contact_and_convert(payload: Bitrix24WebhookPayload) -> ContactPayload:
    """
    Получает контакт из Bitrix24 и преобразует в ContactPayload.

    Args:
        payload: Payload исходящего вебхука с событием OnCrmContactAdd.
    """
    if not payload.auth:
        raise ValueError("Отсутствуют данные авторизации в вебхуке Bitrix24")
    result = _call_bitrix24_api(
        payload.auth.client_endpoint,
        "crm.contact.get",
        payload.auth.access_token,
        {"id": payload.get_entity_id()},
    )
    return contact_to_payload(result)


def fetch_lead_and_convert(payload: Bitrix24WebhookPayload) -> ContactPayload:
    """
    Получает лид из Bitrix24 и преобразует в ContactPayload.

    Args:
        payload: Payload исходящего вебхука с событием OnCrmLeadAdd.
    """
    if not payload.auth:
        raise ValueError("Отсутствуют данные авторизации в вебхуке Bitrix24")
    result = _call_bitrix24_api(
        payload.auth.client_endpoint,
        "crm.lead.get",
        payload.auth.access_token,
        {"id": payload.get_entity_id()},
    )
    return lead_to_payload(result)
