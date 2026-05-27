import logging
from zoneinfo import ZoneInfo

from analyzers.image.factory import ImageEstimator
from core.dates import day_key_for_datetime
from domain.analysis import FoodAnalysis
from domain.photo import Photo, StoredPhoto
from presenters.photo_reply import PHOTO_REPLY_PARSE_MODE, format_photo_reply
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)


async def handle_photo(
    photo: Photo,
    *,
    repo: PhotoRepository,
    image_estimator: ImageEstimator,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    image_bytes: bytes | None = None,
    media_type: str | None = None,
) -> FoodAnalysis | None:
    if not await repo.reserve(photo):
        logger.info("photo already stored, skipping msg=%s", photo.message_id)
        return None

    logger.info(
        "analysing photo chat=%s msg=%s sender=%s",
        photo.chat_id,
        photo.message_id,
        photo.sender_label,
    )

    image_bytes, media_type = await _ensure_image_bytes(
        telegram, photo, image_bytes, media_type
    )

    day_key = day_key_for_datetime(photo.sent_at, timezone)
    eaten_at = photo.sent_at.astimezone(timezone).strftime("%H:%M")
    prior = await repo.estimated_photos_for_user_day(
        chat_id=photo.chat_id, day_key=day_key, sender_label=photo.sender_label
    )
    prior_meals = _format_prior_meals(prior, timezone)

    try:
        analysis = await image_estimator(
            image_bytes,
            media_type,
            photo.caption,
            eaten_at=eaten_at,
            prior_meals=prior_meals,
        )
    except Exception as error:
        logger.exception(
            "failed to analyse photo chat=%s msg=%s",
            photo.chat_id,
            photo.message_id,
        )
        await repo.mark_failed(photo, str(error))
        return None

    logger.info(
        "analysed photo msg=%s dish=%r calories=%s confidence=%s is_food=%s",
        photo.message_id,
        analysis.dish,
        analysis.calories,
        analysis.confidence,
        analysis.is_food,
    )

    await repo.complete(photo, analysis)
    daily_total = await repo.daily_user_total(photo)
    reply = format_photo_reply(photo.sender_label, analysis, daily_total)
    await _safely_reply(telegram, photo, reply, daily_total)
    return analysis


def _format_prior_meals(photos: list[StoredPhoto], timezone: ZoneInfo) -> str:
    parts: list[str] = []
    for stored in photos:
        if not stored.dish:
            continue
        time_label = (
            stored.sent_at.astimezone(timezone).strftime("%H:%M")
            if stored.sent_at
            else ""
        )
        prefix = f"{time_label} " if time_label else ""
        parts.append(f"{prefix}{stored.dish} ({stored.calories} kcal)")
    return "; ".join(parts)


async def _ensure_image_bytes(
    telegram: TelegramBotApi,
    photo: Photo,
    image_bytes: bytes | None,
    media_type: str | None,
) -> tuple[bytes, str]:
    if image_bytes is not None and media_type is not None:
        return image_bytes, media_type
    image_bytes, media_type = await telegram.download_file(photo.file_id)
    logger.info("downloaded photo msg=%s bytes=%s", photo.message_id, len(image_bytes))
    return image_bytes, media_type


async def _safely_reply(
    telegram: TelegramBotApi,
    photo: Photo,
    reply: str,
    daily_total: int,
) -> None:
    try:
        await telegram.send_message(
            chat_id=photo.chat_id,
            text=reply,
            reply_to_message_id=photo.message_id,
            parse_mode=PHOTO_REPLY_PARSE_MODE,
        )
        logger.info(
            "replied chat=%s msg=%s sender=%s total=%s",
            photo.chat_id,
            photo.message_id,
            photo.sender_label,
            daily_total,
        )
    except Exception:
        logger.exception(
            "telegram reply failed chat=%s msg=%s — analysis stored",
            photo.chat_id,
            photo.message_id,
        )
