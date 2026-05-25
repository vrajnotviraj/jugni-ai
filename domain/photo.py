import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class PhotoStatus(StrEnum):
    PENDING = "pending"
    ESTIMATED = "estimated"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Photo:
    update_id: int
    chat_id: int
    message_id: int
    sender_id: int | None
    sender_label: str
    sent_at: datetime
    file_id: str
    file_unique_id: str | None
    caption: str | None

    @classmethod
    def from_telegram_update(cls, update: dict[str, Any]) -> "Photo | None":
        message = update.get("message") or update.get("edited_message") or {}
        photos = message.get("photo") or []
        if not photos:
            return None

        largest = max(photos, key=lambda photo: photo.get("file_size", 0))
        sender = message.get("from") or {}
        caption = (message.get("caption") or "").strip() or None

        return cls(
            update_id=int(update["update_id"]),
            chat_id=int(message["chat"]["id"]),
            message_id=int(message["message_id"]),
            sender_id=sender.get("id"),
            sender_label=_sender_label(sender),
            sent_at=datetime.fromtimestamp(int(message["date"]), tz=UTC),
            file_id=largest["file_id"],
            file_unique_id=largest.get("file_unique_id"),
            caption=caption,
        )

    @classmethod
    def from_local_upload(
        cls,
        *,
        chat_id: int,
        sender_label: str,
        caption: str | None,
        sent_at: datetime | None = None,
    ) -> "Photo":
        synthetic_message_id = -int(time.time() * 1000)
        return cls(
            update_id=0,
            chat_id=chat_id,
            message_id=synthetic_message_id,
            sender_id=None,
            sender_label=sender_label,
            sent_at=sent_at or datetime.now(tz=UTC),
            file_id=f"local:{synthetic_message_id}",
            file_unique_id=None,
            caption=caption,
        )


@dataclass(frozen=True, slots=True)
class StoredPhoto:
    sender_label: str
    calories: int
    message_id: int
    dish: str
    sent_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeletedMeal:
    chat_id: int
    message_id: int
    sender_label: str
    day_key: str
    calories: int
    dish: str
    sent_at: datetime | None


def _sender_label(sender: dict[str, Any]) -> str:
    username = sender.get("username")
    if username:
        return f"@{username}"

    parts = (sender.get("first_name", ""), sender.get("last_name", ""))
    name = " ".join(part for part in parts if part.strip())
    if name:
        return name

    return f"user:{sender.get('id', 'unknown')}"
