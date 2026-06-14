import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class PhotoStatus(StrEnum):
    # PENDING is the "processing" state (reserved, analysis in flight); ESTIMATED is
    # "done" (extraction saved and the meal is logged); FAILED means extraction
    # itself errored. A repeat delivery of a still-PENDING meal raises
    # PhotoStillProcessing so the webhook answers 500 and Telegram retries later.
    PENDING = "pending"
    ESTIMATED = "estimated"
    FAILED = "failed"


class PhotoStillProcessing(Exception):
    """A repeat request arrived while this meal is still being analysed.

    Raised by the photo/intake workflows when a reservation already exists in the
    PENDING state. The webhook turns it into an HTTP 500 so Telegram redelivers the
    update; once analysis reaches ESTIMATED ("done"), the retry answers 200 instead.
    """


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
        message = update.get("message") or {}
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
            sender_label=sender_label_from(sender),
            sent_at=datetime.fromtimestamp(int(message["date"]), tz=UTC),
            file_id=largest["file_id"],
            file_unique_id=largest.get("file_unique_id"),
            caption=caption,
        )

    @classmethod
    def from_text_intake(
        cls,
        *,
        chat_id: int,
        message_id: int,
        sender_id: int | None,
        sender_label: str,
        text: str,
        sent_at: datetime,
    ) -> "Photo":
        # A typed meal (/intake) reuses the photo storage + reply pipeline. There
        # is no file, so file_id is synthetic and file_unique_id is None (which
        # disables image dedup); message_id is the real /intake message so the
        # reply threads back to it and storage keys on it like any other meal.
        # The typed words ride along as the caption, the strongest dish hint.
        return cls(
            update_id=0,
            chat_id=chat_id,
            message_id=message_id,
            sender_id=sender_id,
            sender_label=sender_label,
            sent_at=sent_at,
            file_id=f"text:{message_id}",
            file_unique_id=None,
            caption=text,
        )

    @classmethod
    def from_local_upload(
        cls,
        *,
        chat_id: int,
        sender_label: str,
        caption: str | None,
        sent_at: datetime | None = None,
        sender_id: int | None = None,
    ) -> "Photo":
        # sender_id is optional: pass a real Telegram user id to link the upload to
        # that person's profile (context + timezone); leave it None for an
        # anonymous local upload that gets today's default behavior.
        synthetic_message_id = -int(time.time() * 1000)
        return cls(
            update_id=0,
            chat_id=chat_id,
            message_id=synthetic_message_id,
            sender_id=sender_id,
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
    sender_id: int | None = None
    protein_g: int = 0
    carb_g: int = 0
    fat_g: int = 0
    fibre_g: int = 0
    added_sugar_g: int = 0
    sat_fat_g: int = 0


@dataclass(frozen=True, slots=True)
class DeletedMeal:
    chat_id: int
    message_id: int
    sender_label: str
    day_key: str
    calories: int
    dish: str
    sent_at: datetime | None


@dataclass(frozen=True, slots=True)
class UpdatedMeal:
    chat_id: int
    message_id: int
    sender_label: str
    day_key: str
    dish: str
    calories: int
    previous_calories: int


def sender_label_from(sender: dict[str, Any]) -> str:
    """The display label meals are stored under, from a Telegram ``from`` object.

    Public because command/callback parsing derives the same label to join a
    requester back to their stored meals (see build_recommendation_context).
    """
    username = sender.get("username")
    if username:
        return f"@{username}"

    parts = (sender.get("first_name", ""), sender.get("last_name", ""))
    name = " ".join(part for part in parts if part.strip())
    if name:
        return name

    return f"user:{sender.get('id', 'unknown')}"
