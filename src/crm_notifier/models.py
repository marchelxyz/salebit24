"""Pydantic models for CRM webhook payloads."""

from pydantic import BaseModel, Field


class ContactPayload(BaseModel):
    """Payload from CRM webhook with new contact data."""

    name: str = Field(..., description="Имя контакта")
    phone: str = Field(..., description="Номер телефона")
    title: str | None = Field(default=None, description="Название / источник заявки")
