import logging
from zoneinfo import ZoneInfo

from analyzers.image.factory import ImageEstimator
from core.dates import day_key_for_datetime
from domain.analysis import FoodAnalysis
from domain.calorie_target import goal_summary
from domain.photo import Photo, StoredPhoto
from presenters.photo_reply import (
    PHOTO_REPLY_PARSE_MODE,
    format_photo_reply,
    format_streak_line,
)
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from workflows.personalization import dietary_facts
from workflows.streak import user_streak

logger = logging.getLogger(__name__)


async def handle_photo(
    photo: Photo,
    *,
    repo: PhotoRepository,
    image_estimator: ImageEstimator,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    profile_repo: ProfileRepository | None = None,
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

    # Personalization is best-effort and forward-looking: senderless uploads
    # (sender_id is None) and people without a profile see today's exact behavior.
    profile = await _load_profile(profile_repo, photo)
    # Day bucketing stays on the app timezone (group summary coherence, KTD6);
    # only the tip's clock follows the sender's own timezone.
    user_zone = profile.zone(timezone) if profile else timezone

    day_key = day_key_for_datetime(photo.sent_at, timezone)
    eaten_at = photo.sent_at.astimezone(user_zone).strftime("%H:%M")
    prior = await repo.estimated_photos_for_user_day(
        chat_id=photo.chat_id, day_key=day_key, sender_label=photo.sender_label
    )
    prior_meals = _format_prior_meals(prior, user_zone)
    personal_context = await dietary_facts(profile, profile_repo, photo.sender_id)
    personal_goal = goal_summary(profile)

    logger.info(
        "photo context msg=%s sender_id=%s has_profile=%s goal=%r tz=%s "
        "context_chars=%s prior_meals=%s",
        photo.message_id,
        photo.sender_id,
        profile is not None,
        personal_goal,
        user_zone.key,
        len(personal_context) if personal_context else 0,
        bool(prior_meals),
    )

    try:
        analysis = await image_estimator(
            image_bytes,
            media_type,
            photo.caption,
            eaten_at=eaten_at,
            prior_meals=prior_meals,
            personal_context=personal_context,
            personal_goal=personal_goal,
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
    # Reinforce the streak only on the first meal of the local day (KTD4); `prior`
    # was read before this photo was stored, so empty means this is the first.
    streak_line = await _streak_line(repo, photo, day_key) if not prior else None
    reply = format_photo_reply(
        photo.sender_label, analysis, daily_total, streak_line=streak_line
    )
    await _safely_reply(telegram, photo, reply, daily_total)
    return analysis


async def _streak_line(
    repo: PhotoRepository,
    photo: Photo,
    day_key: str,
) -> str | None:
    # Defensive, mirroring the macro line: a streak failure must never block the
    # calorie reply.
    try:
        state = await user_streak(
            repo=repo,
            chat_id=photo.chat_id,
            sender_label=photo.sender_label,
            as_of_day_key=day_key,
        )
        return format_streak_line(state)
    except Exception:
        logger.exception(
            "streak line failed msg=%s; replying without it", photo.message_id
        )
        return None


async def _load_profile(
    profile_repo: ProfileRepository | None,
    photo: Photo,
):
    if profile_repo is None or photo.sender_id is None:
        return None
    return await profile_repo.get_profile(photo.sender_id)


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
