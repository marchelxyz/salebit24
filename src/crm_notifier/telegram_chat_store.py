"""Хранилище chat_id для уведомлений (in-memory, без БД)."""

_registered_chat_id: str | None = None


def set_chat_id(chat_id: str | int) -> None:
    """Сохраняет chat_id пользователя, отправившего /start боту."""
    global _registered_chat_id
    _registered_chat_id = str(chat_id)


def get_chat_id() -> str | None:
    """Возвращает сохранённый chat_id или None."""
    return _registered_chat_id
