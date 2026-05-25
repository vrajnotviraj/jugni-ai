import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import (
    admin_secret_header,
    get_repo,
    get_settings,
    get_telegram,
    resolve_target_chat_id,
    verify_admin_secret,
)
from core.dates import day_key_for_day_iso, today_day_key
from core.settings import Settings
from domain.photo import StoredPhoto
from presenters.meal_deleted import MEAL_DELETED_PARSE_MODE, format_meal_deleted
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meals", tags=["meals"])


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

    deleted = await repo.delete_meal(chat_id=target_chat_id, message_id=message_id)
    if deleted is None:
        raise HTTPException(
            status_code=404,
            detail=f"Meal {message_id} not found in chat {target_chat_id}.",
        )

    new_total = await repo.daily_user_calories(
        chat_id=target_chat_id,
        day_key=deleted.day_key,
        sender_label=deleted.sender_label,
    )

    notified = False
    if notify:
        notified = await _notify_meal_deleted(
            telegram=telegram,
            chat_id=target_chat_id,
            sender_label=deleted.sender_label,
            dish=deleted.dish,
            calories=deleted.calories,
            new_total_calories=new_total,
            day_key=deleted.day_key,
            today_key=today_day_key(settings.timezone),
        )

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
        "new_total_calories": new_total,
        "notified": notified,
    }


async def _notify_meal_deleted(
    *,
    telegram: TelegramBotApi,
    chat_id: int,
    sender_label: str,
    dish: str,
    calories: int,
    new_total_calories: int,
    day_key: str,
    today_key: str,
) -> bool:
    text = format_meal_deleted(
        sender_label=sender_label,
        dish=dish,
        calories=calories,
        new_total_calories=new_total_calories,
        day_key=day_key,
        today_key=today_key,
    )
    try:
        await telegram.send_message(chat_id, text, parse_mode=MEAL_DELETED_PARSE_MODE)
    except Exception:
        logger.exception(
            "Failed to send meal-deleted notice chat=%s sender=%s",
            chat_id,
            sender_label,
        )
        return False
    return True


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
