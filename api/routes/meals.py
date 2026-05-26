import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.dependencies import (
    admin_secret_header,
    get_repo,
    get_settings,
    get_telegram,
    resolve_target_chat_id,
    verify_admin_secret,
)
from controllers.delete_meal import run_meal_deletion
from controllers.meal_notifications import notify_meal_updated
from core.dates import day_key_for_day_iso, today_day_key
from core.settings import Settings
from domain.photo import StoredPhoto
from presenters.meals_csv import CSV_MIME_TYPE, build_meals_csv, csv_filename
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meals", tags=["meals"])


class UpdateMealRequest(BaseModel):
    calories: int = Field(ge=0, description="New calorie count for the meal.")


@router.get("")
async def list_all_meals(
    date: str | None = Query(default=None, description="ISO date, defaults to today."),
    chat_id: int | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    target_chat_id = resolve_target_chat_id(settings, chat_id)
    day_key = _resolve_day(settings, date)

    photos = await repo.estimated_photos_for_day(
        chat_id=target_chat_id, day_key=day_key
    )

    return {
        "ok": True,
        "chat_id": target_chat_id,
        "day": day_key,
        "total_meals": len(photos),
        "users": _group_by_user(photos),
    }


@router.get("/person/{person}")
async def list_person_meals(
    person: str,
    date: str | None = Query(default=None, description="ISO date, defaults to today."),
    chat_id: int | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    target_chat_id = resolve_target_chat_id(settings, chat_id)
    day_key = _resolve_day(settings, date)

    photos = await repo.estimated_photos_for_day(
        chat_id=target_chat_id, day_key=day_key
    )
    matched = [p for p in photos if _matches_person(p.sender_label, person)]
    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"No meals found for '{person}' on {day_key}.",
        )

    return {
        "ok": True,
        "chat_id": target_chat_id,
        "day": day_key,
        "sender_label": matched[0].sender_label,
        "total_calories": sum(p.calories for p in matched),
        "meals": [_meal_payload(p) for p in matched],
    }


@router.get("/report")
async def meals_report(
    person: str = Query(
        ...,
        description="Sender label (case- and '@'-insensitive). Required.",
    ),
    days: int = Query(
        default=7,
        ge=1,
        le=30,
        description="Number of days ending today (inclusive).",
    ),
    chat_id: int | None = Query(default=None),
    send: bool = Query(
        default=True,
        description="Also send the CSV to the Telegram chat as a document.",
    ),
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    telegram: TelegramBotApi = Depends(get_telegram),
    admin_secret: str | None = Depends(admin_secret_header),
) -> Response:
    verify_admin_secret(settings, admin_secret)
    target_chat_id = resolve_target_chat_id(settings, chat_id)

    day_keys = _last_n_day_keys(today_day_key(settings.timezone), days)
    photos_by_day = await repo.estimated_photos_for_range(
        chat_id=target_chat_id, day_keys=day_keys
    )
    photos_by_day = _filter_by_person(photos_by_day, person)
    canonical_label = _canonical_person_label(photos_by_day) or person.strip()

    csv_bytes = build_meals_csv(
        chat_id=target_chat_id,
        photos_by_day=photos_by_day,
        timezone=settings.timezone,
    )
    filename = csv_filename(start=day_keys[0], end=day_keys[-1], person=canonical_label)
    total_meals = sum(len(photos) for photos in photos_by_day.values())
    total_calories = sum(
        photo.calories for photos in photos_by_day.values() for photo in photos
    )

    notified = False
    if send:
        caption = (
            f"📊 {canonical_label}'s meals {day_keys[0]} → {day_keys[-1]}\n"
            f"{total_meals} meals · {total_calories} kcal"
        )
        notified = await _send_csv_to_chat(
            telegram=telegram,
            chat_id=target_chat_id,
            filename=filename,
            content=csv_bytes,
            caption=caption,
        )

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Meals-Report-Person": canonical_label,
        "X-Meals-Report-From": day_keys[0],
        "X-Meals-Report-To": day_keys[-1],
        "X-Meals-Report-Total-Meals": str(total_meals),
        "X-Meals-Report-Total-Calories": str(total_calories),
        "X-Meals-Report-Notified": "1" if notified else "0",
    }
    return Response(content=csv_bytes, media_type=CSV_MIME_TYPE, headers=headers)


@router.delete("/{message_id}")
async def delete_meal(
    message_id: int,
    chat_id: int | None = Query(default=None),
    notify: bool = Query(
        default=True,
        description="Send a Telegram notice to the chat.",
    ),
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    telegram: TelegramBotApi = Depends(get_telegram),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    target_chat_id = resolve_target_chat_id(settings, chat_id)

    result = await run_meal_deletion(
        repo=repo,
        telegram=telegram,
        timezone=settings.timezone,
        chat_id=target_chat_id,
        message_id=message_id,
        notify=notify,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Meal {message_id} not found in chat {target_chat_id}.",
        )

    deleted = result.deleted
    return {
        "ok": True,
        "chat_id": target_chat_id,
        "day": deleted.day_key,
        "deleted": {
            "message_id": deleted.message_id,
            "sender_label": deleted.sender_label,
            "dish": deleted.dish,
            "calories": deleted.calories,
            "eaten_at": deleted.sent_at.isoformat() if deleted.sent_at else None,
        },
        "new_total_calories": result.new_total_calories,
        "notified": result.notified,
    }


@router.patch("/{message_id}")
async def update_meal(
    message_id: int,
    payload: UpdateMealRequest,
    chat_id: int | None = Query(default=None),
    notify: bool = Query(
        default=True,
        description="Send a Telegram notice to the chat.",
    ),
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    telegram: TelegramBotApi = Depends(get_telegram),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    target_chat_id = resolve_target_chat_id(settings, chat_id)

    updated = await repo.update_meal_calories(
        chat_id=target_chat_id,
        message_id=message_id,
        calories=payload.calories,
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Meal {message_id} not found in chat {target_chat_id}.",
        )

    new_total = await repo.daily_user_calories(
        chat_id=target_chat_id,
        day_key=updated.day_key,
        sender_label=updated.sender_label,
    )

    notified = False
    if notify and updated.calories != updated.previous_calories:
        notified = await notify_meal_updated(
            telegram=telegram,
            chat_id=target_chat_id,
            sender_label=updated.sender_label,
            dish=updated.dish,
            previous_calories=updated.previous_calories,
            new_calories=updated.calories,
            new_total_calories=new_total,
            day_key=updated.day_key,
            today_key=today_day_key(settings.timezone),
        )

    return {
        "ok": True,
        "chat_id": target_chat_id,
        "day": updated.day_key,
        "meal": {
            "message_id": updated.message_id,
            "sender_label": updated.sender_label,
            "dish": updated.dish,
            "calories": updated.calories,
            "previous_calories": updated.previous_calories,
        },
        "new_total_calories": new_total,
        "notified": notified,
    }


async def _send_csv_to_chat(
    *,
    telegram: TelegramBotApi,
    chat_id: int,
    filename: str,
    content: bytes,
    caption: str,
) -> bool:
    try:
        await telegram.send_document(
            chat_id,
            filename,
            content,
            mime_type=CSV_MIME_TYPE,
            caption=caption,
        )
    except Exception:
        logger.exception("Failed to send meals CSV to chat=%s", chat_id)
        return False
    return True


def _last_n_day_keys(today_iso: str, days: int) -> list[str]:
    today = date.fromisoformat(today_iso)
    return [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _resolve_day(settings: Settings, date: str | None) -> str:
    if not date:
        return today_day_key(settings.timezone)
    try:
        return day_key_for_day_iso(date)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid date. Use YYYY-MM-DD.",
        ) from error


def _matches_person(sender_label: str, needle: str) -> bool:
    return _normalize(sender_label) == _normalize(needle)


def _normalize(value: str) -> str:
    return value.strip().lstrip("@").casefold()


def _filter_by_person(
    photos_by_day: dict[str, list[StoredPhoto]],
    person: str,
) -> dict[str, list[StoredPhoto]]:
    return {
        day_key: [p for p in photos if _matches_person(p.sender_label, person)]
        for day_key, photos in photos_by_day.items()
    }


def _canonical_person_label(
    photos_by_day: dict[str, list[StoredPhoto]],
) -> str | None:
    for photos in photos_by_day.values():
        if photos:
            return photos[0].sender_label
    return None


def _group_by_user(photos: list[StoredPhoto]) -> list[dict[str, Any]]:
    grouped: dict[str, list[StoredPhoto]] = {}
    order: list[str] = []
    for photo in photos:
        if photo.sender_label not in grouped:
            grouped[photo.sender_label] = []
            order.append(photo.sender_label)
        grouped[photo.sender_label].append(photo)

    return [
        {
            "sender_label": label,
            "total_calories": sum(p.calories for p in grouped[label]),
            "meals": [_meal_payload(p) for p in grouped[label]],
        }
        for label in order
    ]


def _meal_payload(photo: StoredPhoto) -> dict[str, Any]:
    return {
        "message_id": photo.message_id,
        "dish": photo.dish,
        "calories": photo.calories,
        "eaten_at": photo.sent_at.isoformat() if photo.sent_at else None,
    }
