import json
from datetime import datetime
from typing import Any

from domain.analysis import CONFIDENCE_LEVELS, FoodAnalysis
from domain.photo import Photo, PhotoStatus, StoredPhoto


def photo_to_hash(
    photo: Photo,
    day_key: str,
    status: PhotoStatus = PhotoStatus.PENDING,
    content_hash: str | None = None,
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
    if content_hash is not None:
        fields["content_hash"] = content_hash
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
        "protein_g": analysis.protein_g,
        "carb_g": analysis.carb_g,
        "fat_g": analysis.fat_g,
        "fibre_g": analysis.fibre_g,
        "added_sugar_g": analysis.added_sugar_g,
        "sat_fat_g": analysis.sat_fat_g,
        # JSON-encoded so the per-item breakdown survives a reload and a reused
        # duplicate reply shows the same "What's in it" card as the first one.
        "items": json.dumps(list(analysis.items)),
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
        sender_id=_sender_id(raw.get("sender_id")),
        protein_g=_macro_int(raw.get("protein_g")),
        carb_g=_macro_int(raw.get("carb_g")),
        fat_g=_macro_int(raw.get("fat_g")),
        fibre_g=_macro_int(raw.get("fibre_g")),
        added_sugar_g=_macro_int(raw.get("added_sugar_g")),
        sat_fat_g=_macro_int(raw.get("sat_fat_g")),
    )


def analysis_from_hash(raw: dict[str, Any]) -> FoodAnalysis | None:
    if not raw or raw.get("status") != PhotoStatus.ESTIMATED.value:
        return None

    calories_raw = raw.get("calories")
    if calories_raw in (None, ""):
        return None
    try:
        calories = int(calories_raw)
    except (TypeError, ValueError):
        return None

    confidence = raw.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "medium"

    return FoodAnalysis(
        dish=raw.get("dish", "Unknown dish"),
        calories=calories,
        confidence=confidence,
        tip=raw.get("tip", ""),
        is_food=raw.get("is_food") == "1",
        protein_g=_macro_int(raw.get("protein_g")),
        carb_g=_macro_int(raw.get("carb_g")),
        fat_g=_macro_int(raw.get("fat_g")),
        fibre_g=_macro_int(raw.get("fibre_g")),
        added_sugar_g=_macro_int(raw.get("added_sugar_g")),
        sat_fat_g=_macro_int(raw.get("sat_fat_g")),
        items=_decode_items(raw.get("items")),
    )


def _sender_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _macro_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _decode_items(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        return ()
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(
        item.strip() for item in data if isinstance(item, str) and item.strip()
    )


def _parse_sent_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
