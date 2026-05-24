import logging
from dataclasses import asdict
from datetime import UTC, datetime
from datetime import time as dtime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.dependencies import (
    admin_secret_header,
    get_image_estimator,
    get_repo,
    get_settings,
    get_telegram,
    resolve_target_chat_id,
    verify_admin_secret,
)
from controllers.handle_photo import handle_photo
from core.settings import Settings
from domain.photo import Photo
from image_analyser.factory import ImageEstimator
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi

router = APIRouter()

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/api/upload")
async def upload_food_photo(
    image: UploadFile = File(...),
    user_label: str = Form(...),
    chat_id: int | None = Form(default=None),
    caption: str | None = Form(default=None),
    time: str | None = Form(
        default=None,
        description="Local HH:MM the food was eaten.",
    ),
    settings: Settings = Depends(get_settings),
    telegram: TelegramBotApi = Depends(get_telegram),
    repo: PhotoRepository = Depends(get_repo),
    image_estimator: ImageEstimator = Depends(get_image_estimator),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    target_chat_id = resolve_target_chat_id(settings, chat_id)

    image_bytes = await image.read(MAX_UPLOAD_BYTES + 1)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image upload is too large.")

    media_type = _upload_media_type(image)
    if media_type not in ALLOWED_UPLOAD_MEDIA_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type. Use JPEG, PNG, or WEBP.",
        )
    sender_label = user_label.strip() or "@local"
    photo_caption = (caption or "").strip() or None
    sent_at = _resolve_sent_at(settings, time)

    logger.info(
        "upload received chat=%s user=%s bytes=%s media=%s caption=%r sent_at=%s",
        target_chat_id,
        sender_label,
        len(image_bytes),
        media_type,
        photo_caption,
        sent_at.isoformat(),
    )

    photo = Photo.from_local_upload(
        chat_id=target_chat_id,
        sender_label=sender_label,
        caption=photo_caption,
        sent_at=sent_at,
    )

    analysis = await handle_photo(
        photo,
        repo=repo,
        image_estimator=image_estimator,
        telegram=telegram,
        image_bytes=image_bytes,
        media_type=media_type,
    )

    if analysis is None:
        raise HTTPException(
            status_code=500,
            detail="Analysis failed. Check server logs.",
        )

    return {"ok": True, "chat_id": target_chat_id, "analysis": asdict(analysis)}


def _resolve_sent_at(settings: Settings, time_hhmm: str | None) -> datetime:
    if not time_hhmm:
        return datetime.now(tz=UTC)

    cleaned = time_hhmm.strip()
    try:
        parsed = dtime.fromisoformat(cleaned)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid time. Use HH:MM (24-hour), e.g. 09:30.",
        ) from error

    today_local = datetime.now(tz=settings.timezone).date()
    local_dt = datetime.combine(today_local, parsed, tzinfo=settings.timezone)
    return local_dt.astimezone(UTC)


def _upload_media_type(image: UploadFile) -> str:
    if image.content_type in ALLOWED_UPLOAD_MEDIA_TYPES:
        return image.content_type
    filename = (image.filename or "").lower()
    if filename.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if filename.endswith(".png"):
        return "image/png"
    if filename.endswith(".webp"):
        return "image/webp"
    return image.content_type or "application/octet-stream"
