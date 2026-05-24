from datetime import datetime
from typing import Any

from domain.analysis import FoodAnalysis
from domain.photo import Photo, PhotoStatus, StoredPhoto


def photo_to_hash(
    photo: Photo,
    day_key: str,
    status: PhotoStatus = PhotoStatus.PENDING,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "telegram_update_id": photo.update_id,
        "chat_id": photo.chat_id,
        "message_id": photo.message_id,
        "sender_label": photo.sender_label,
        "sent_at": photo.sent_at.isoformat(),
        "file_id": photo.file_id,
        "day": day_key,
        "status": status.value,
    }
    if photo.sender_id is not None:
        fields["sender_id"] = photo.sender_id
    if photo.file_unique_id is not None:
        fields["file_unique_id"] = photo.file_unique_id
    if photo.caption is not None:
        fields["caption"] = photo.caption
    return fields


def analysis_to_fields(analysis: FoodAnalysis) -> dict[str, Any]:
    return {
        "status": PhotoStatus.ESTIMATED.value,
        "calories": analysis.calories,
        "dish": analysis.dish,
        "confidence": analysis.confidence,
        "tip": analysis.tip,
        "is_food": 1 if analysis.is_food else 0,
    }


def failure_to_fields(error: str) -> dict[str, Any]:
    return {"status": PhotoStatus.FAILED.value, "error": error[:500]}


def photo_from_hash(raw: dict[str, Any]) -> StoredPhoto | None:
    if not raw:
        return None
    if raw.get("status") != PhotoStatus.ESTIMATED.value:
        return None
    if raw.get("is_food") != "1":
        return None

    calories_raw = raw.get("calories")
    if calories_raw in (None, ""):
        return None
    try:
        calories = int(calories_raw)
    except (TypeError, ValueError):
        return None

    sent_at = _parse_sent_at(raw.get("sent_at"))
    return StoredPhoto(
        sender_label=raw["sender_label"],
        calories=calories,
        message_id=int(raw["message_id"]),
        dish=raw.get("dish", ""),
        sent_at=sent_at,
    )


def _parse_sent_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
