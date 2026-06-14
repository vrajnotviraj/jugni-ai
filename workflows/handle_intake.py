import logging
from zoneinfo import ZoneInfo

from analyzers.intake.factory import IntakeAnalyzer
from core.dates import day_key_for_datetime
from domain.analysis import FoodAnalysis
from domain.calorie_target import calorie_target, goal_summary, protein_target_g
from domain.photo import Photo, PhotoStatus, PhotoStillProcessing, StoredPhoto
from presenters.photo_reply import (
    PHOTO_REPLY_PARSE_MODE,
    format_photo_reply,
    format_streak_line,
)
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import IntakeCommand
from workflows.personalization import dietary_facts
from workflows.streak import user_streak

logger = logging.getLogger(__name__)

USAGE_REPLY = (
    "Tell me what you ate in words, e.g.\n"
    "/intake 2 rotli and a katori of dal\n"
    "/intake 2 blocks dark chocolate + 10g almonds"
)
LOGGING_REPLY = "🔍 Looking up your meal…"
INTAKE_FAILED_REPLY = (
    "⚠️ Couldn't read that one. Try naming the items and portions, "
    "or send a photo of the plate."
)
NOT_FOOD_REPLY = (
    "That doesn't look like food I can log. Tell me what you ate, "
    "e.g. /intake 2 rotli and a katori of dal."
)
LOW_CONFIDENCE_REPLY = (
    "I couldn't pin that down well enough to log it honestly — too vague or too "
    "heavy a meal for words. Add the portions, or just send a photo of the plate."
)


async def handle_intake(
    command: IntakeCommand,
    *,
    repo: PhotoRepository,
    profile_repo: ProfileRepository,
    intake_analyzer: IntakeAnalyzer,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
) -> FoodAnalysis | None:
    text = command.text.strip()
    if not text:
        await _deliver(telegram, command, USAGE_REPLY, None)
        return None

    # Mirror the photo path: resolve the profile first so the meal buckets into
    # the sender's own local day and the coaching pass can personalize.
    profile = await profile_repo.get_profile(command.user_id)
    user_zone = profile.zone(timezone) if profile else timezone
    day_key = day_key_for_datetime(command.sent_at, user_zone)

    photo = Photo.from_text_intake(
        chat_id=command.chat_id,
        message_id=command.message_id,
        sender_id=command.user_id,
        sender_label=command.sender_label,
        text=text,
        sent_at=command.sent_at,
    )

    # Reserve before any work (and before the placeholder) so a repeat /intake of
    # the same message locks: a still-running one signals 500 so Telegram retries
    # once it's done, a finished one just acks. The reservation for a meal we end
    # up rejecting (non-food, too vague) is discarded below, so nothing is stored.
    if not await repo.reserve(photo, day_key=day_key):
        if await repo.status(photo) == PhotoStatus.PENDING:
            logger.info(
                "intake still processing msg=%s; signalling retry", command.message_id
            )
            raise PhotoStillProcessing
        logger.info("intake already stored, skipping msg=%s", command.message_id)
        return None

    async def _discard() -> None:
        await repo.delete_meal(chat_id=photo.chat_id, message_id=photo.message_id)

    placeholder_id = await _send_placeholder(telegram, command)

    eaten_at = command.sent_at.astimezone(user_zone).strftime("%H:%M")
    eaten_at_label = eaten_at if profile and profile.timezone else None
    prior = await repo.estimated_photos_for_user_day(
        chat_id=command.chat_id, day_key=day_key, sender_label=command.sender_label
    )
    prior_meals = _format_prior_meals(prior, user_zone)
    personal_context = await dietary_facts(profile, profile_repo, command.user_id)
    target = calorie_target(profile)
    personal_goal = goal_summary(profile, target)
    protein_target = protein_target_g(profile)
    protein_so_far = sum(stored.protein_g for stored in prior)

    logger.info(
        "intake chat=%s msg=%s sender=%s has_profile=%s text_len=%d",
        command.chat_id,
        command.message_id,
        command.sender_label,
        profile is not None,
        len(text),
    )

    async def _persist_extraction(extraction: FoodAnalysis) -> None:
        # Save + mark "done" the moment extraction lands, but only when the typed
        # meal is actually loggable; non-food/too-vague intakes are never stored
        # (their reservation is discarded below). The tip is added later via set_tip.
        if _is_loggable(extraction):
            await repo.complete(photo, extraction)

    try:
        analysis = await intake_analyzer(
            text,
            sender_label=command.sender_label,
            eaten_at=eaten_at,
            prior_meals=prior_meals,
            personal_context=personal_context,
            personal_goal=personal_goal,
            protein_so_far_g=protein_so_far,
            protein_target_g=protein_target,
            on_extracted=_persist_extraction,
        )
    except Exception:
        logger.exception(
            "failed to analyse intake chat=%s msg=%s",
            command.chat_id,
            command.message_id,
        )
        await _discard()
        await _deliver(telegram, command, INTAKE_FAILED_REPLY, placeholder_id)
        return None

    logger.info(
        "analysed intake msg=%s dish=%r calories=%s confidence=%s is_food=%s",
        command.message_id,
        analysis.dish,
        analysis.calories,
        analysis.confidence,
        analysis.is_food,
    )

    # Text intake is meant for simple items; anything we can't size honestly is
    # rejected rather than logged with a wrong number. The hook above stored
    # nothing for these, so discard the reservation to leave no trace in the tally.
    if not analysis.is_food:
        await _discard()
        await _deliver(telegram, command, NOT_FOOD_REPLY, placeholder_id)
        return analysis
    if analysis.confidence == "low":
        await _discard()
        await _deliver(telegram, command, LOW_CONFIDENCE_REPLY, placeholder_id)
        return analysis

    # Extraction was saved and the meal marked "done" via the hook; attach the tip.
    if analysis.tip:
        await repo.set_tip(photo, analysis.tip)

    daily_total = await repo.daily_user_calories(
        chat_id=command.chat_id, day_key=day_key, sender_label=command.sender_label
    )
    # Reinforce the streak only on the first meal of the local day; `prior` was
    # read before this meal was stored, so empty means this is the first.
    streak_line = await _streak_line(repo, photo, day_key) if not prior else None
    reply = format_photo_reply(
        command.sender_label,
        analysis,
        daily_total,
        streak_line=streak_line,
        eaten_at=eaten_at_label,
        calorie_target=target,
        protein_today_g=protein_so_far + max(0, analysis.protein_g),
        protein_target_g=protein_target,
    )
    await _deliver(telegram, command, reply, placeholder_id)
    return analysis


def _is_loggable(analysis: FoodAnalysis) -> bool:
    """Whether a typed meal is worth storing: real food we can size honestly. A
    low-confidence reading is too vague to log with a number we'd stand behind."""
    return analysis.is_food and analysis.confidence != "low"


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


async def _streak_line(
    repo: PhotoRepository,
    photo: Photo,
    day_key: str,
) -> str | None:
    # Defensive: a streak failure must never block the calorie reply.
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


async def _send_placeholder(
    telegram: TelegramBotApi, command: IntakeCommand
) -> int | None:
    try:
        return await telegram.send_message(
            chat_id=command.chat_id,
            text=LOGGING_REPLY,
            reply_to_message_id=command.message_id,
        )
    except Exception:
        logger.exception(
            "intake placeholder send failed chat=%s msg=%s",
            command.chat_id,
            command.message_id,
        )
        return None


async def _deliver(
    telegram: TelegramBotApi,
    command: IntakeCommand,
    text: str,
    placeholder_id: int | None,
) -> None:
    """Show the result: edit the placeholder in place, or send fresh when there
    was no placeholder (usage reply) or the edit fails."""
    if placeholder_id is not None:
        try:
            await telegram.edit_message_text(
                chat_id=command.chat_id,
                message_id=placeholder_id,
                text=text,
                parse_mode=PHOTO_REPLY_PARSE_MODE,
            )
            return
        except Exception:
            logger.exception(
                "intake placeholder edit failed chat=%s msg=%s — sending fresh",
                command.chat_id,
                command.message_id,
            )

    try:
        await telegram.send_message(
            chat_id=command.chat_id,
            text=text,
            reply_to_message_id=command.message_id,
            parse_mode=PHOTO_REPLY_PARSE_MODE,
        )
    except Exception:
        logger.exception(
            "intake reply failed chat=%s msg=%s",
            command.chat_id,
            command.message_id,
        )
