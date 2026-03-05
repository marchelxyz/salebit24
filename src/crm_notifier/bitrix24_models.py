"""Модели для payload исходящих вебхуков Bitrix24."""

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Bitrix24Auth(BaseModel):
    """Данные авторизации из webhook Bitrix24."""

    model_config = {"extra": "ignore"}

    access_token: str = Field(..., description="OAuth access token")
    expires_in: int | str = Field(..., description="Время жизни токена")
    scope: str = Field(default="crm", description="Scope")
    domain: str = Field(default="", description="Домен Bitrix24")
    client_endpoint: str = Field(..., description="URL для REST API")

    @field_validator("expires_in")
    @classmethod
    def _coerce_expires_in(cls, v: int | str) -> int:
        return int(v) if v is not None else 0


class Bitrix24Fields(BaseModel):
    """Поля из data.FIELDS в webhook."""

    model_config = {"extra": "ignore"}

    ID: str | int = Field(..., description="ID сущности (контакт или лид)")


class Bitrix24Data(BaseModel):
    """Данные события из webhook."""

    model_config = {"extra": "ignore"}

    FIELDS: Bitrix24Fields


class Bitrix24WebhookPayload(BaseModel):
    """Payload исходящего вебхука Bitrix24 (event handler)."""

    model_config = {"extra": "ignore"}

    event: str = Field(..., description="Код события (ONCRMCONTACTADD, ONCRMLEADADD)")
    event_handler_id: str | None = Field(default=None)
    data: Bitrix24Data = Field(..., description="Данные события")
    ts: str | None = Field(default=None)
    auth: Bitrix24Auth | None = Field(default=None)

    def get_entity_id(self) -> int:
        """Возвращает ID контакта или лида."""
        raw = self.data.FIELDS.ID
        return int(raw) if raw is not None else 0


def _ensure_rest_url(endpoint: str) -> str:
    """Добавляет протокол и /rest/ если нужно."""
    s = str(endpoint).strip()
    if not s:
        return s
    if not s.startswith("http"):
        s = "https://" + s
    return s.rstrip("/") + "/" if not s.endswith("/") else s


def parse_bitrix24_payload_flexible(body: dict[str, Any]) -> Bitrix24WebhookPayload | None:
    """
    Пытается извлечь payload из тела запроса с разными форматами Bitrix24.
    """
    event = body.get("event") or body.get("EVENT")
    if not event:
        return None

    entity_id: int | None = None
    data = body.get("data") or body.get("DATA")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = None
    if isinstance(data, dict):
        fields = data.get("FIELDS") or data.get("fields")
        if isinstance(fields, dict):
            raw_id = fields.get("ID") or fields.get("id")
            if raw_id is not None:
                entity_id = int(raw_id)
    if entity_id is None and body.get("id") is not None:
        entity_id = int(body["id"])
    if entity_id is None:
        return None

    auth_raw = body.get("auth") or body.get("AUTH")
    if isinstance(auth_raw, str):
        try:
            auth_raw = json.loads(auth_raw)
        except json.JSONDecodeError:
            auth_raw = None
    if not isinstance(auth_raw, dict):
        return None

    access_token = auth_raw.get("access_token") or auth_raw.get("ACCESS_TOKEN")
    client_endpoint = auth_raw.get("client_endpoint") or auth_raw.get("CLIENT_ENDPOINT")
    if not access_token or not client_endpoint:
        return None

    client_endpoint = _ensure_rest_url(client_endpoint)
    domain = auth_raw.get("domain") or auth_raw.get("DOMAIN") or ""
    if not domain and client_endpoint:
        domain = client_endpoint.replace("https://", "").replace("http://", "").split("/")[0]

    return Bitrix24WebhookPayload(
        event=str(event),
        data=Bitrix24Data(FIELDS=Bitrix24Fields(ID=entity_id)),
        auth=Bitrix24Auth(
            access_token=str(access_token),
            expires_in=auth_raw.get("expires_in") or auth_raw.get("EXPIRES_IN") or 3600,
            scope=str(auth_raw.get("scope") or auth_raw.get("SCOPE") or "crm"),
            domain=str(domain),
            client_endpoint=client_endpoint,
        ),
    )


def _extract_phone(phone_list: list[dict[str, Any]] | None) -> str:
    """Извлекает первый номер телефона из массива Bitrix24."""
    if not phone_list:
        return "Не указан"
    for item in phone_list:
        if isinstance(item, dict) and item.get("VALUE"):
            return str(item["VALUE"])
    return "Не указан"


def _build_name(*parts: str | None) -> str:
    """Собирает полное имя из частей."""
    name = " ".join(p for p in parts if p and str(p).strip()).strip()
    return name or "Без имени"


def contact_to_payload(result: dict[str, Any]) -> "ContactPayload":
    """Преобразует результат crm.contact.get в ContactPayload."""
    from src.crm_notifier.models import ContactPayload

    name = _build_name(
        result.get("NAME"),
        result.get("SECOND_NAME"),
        result.get("LAST_NAME"),
    )
    phone = _extract_phone(result.get("PHONE"))
    title = result.get("SOURCE_DESCRIPTION") or result.get("POST") or None
    return ContactPayload(name=name, phone=phone, title=title)


def lead_to_payload(result: dict[str, Any]) -> "ContactPayload":
    """Преобразует результат crm.lead.get в ContactPayload."""
    from src.crm_notifier.models import ContactPayload

    name = _build_name(result.get("NAME"), result.get("LAST_NAME"))
    phone = _extract_phone(result.get("PHONE"))
    title = result.get("TITLE") or result.get("SOURCE_DESCRIPTION") or None
    return ContactPayload(name=name, phone=phone, title=title)
