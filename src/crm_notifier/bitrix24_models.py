"""Модели для payload исходящих вебхуков Bitrix24."""

from typing import Any

from pydantic import BaseModel, Field


class Bitrix24Auth(BaseModel):
    """Данные авторизации из webhook Bitrix24."""

    access_token: str = Field(..., description="OAuth access token")
    expires_in: int = Field(..., description="Время жизни токена в секундах")
    scope: str = Field(..., description="Scope")
    domain: str = Field(..., description="Домен Bitrix24")
    client_endpoint: str = Field(..., description="URL для REST API")


class Bitrix24Fields(BaseModel):
    """Поля из data.FIELDS в webhook."""

    ID: str | int = Field(..., description="ID сущности (контакт или лид)")


class Bitrix24Data(BaseModel):
    """Данные события из webhook."""

    FIELDS: Bitrix24Fields


class Bitrix24WebhookPayload(BaseModel):
    """Payload исходящего вебхука Bitrix24 (event handler)."""

    event: str = Field(..., description="Код события (ONCRMCONTACTADD, ONCRMLEADADD)")
    event_handler_id: str | None = Field(default=None)
    data: Bitrix24Data = Field(..., description="Данные события")
    ts: str | None = Field(default=None)
    auth: Bitrix24Auth | None = Field(default=None)

    def get_entity_id(self) -> int:
        """Возвращает ID контакта или лида."""
        raw = self.data.FIELDS.ID
        return int(raw) if raw is not None else 0


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
