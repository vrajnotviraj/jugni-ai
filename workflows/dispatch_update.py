import logging
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from analyzers.context.rewriter import ContextRewriter
from analyzers.image.factory import ImageEstimator
from analyzers.profile.extractor import ProfileExtractor
from analyzers.summary.factory import DaySummarizer
from core.dates import today_day_key
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import (
    AddContextCommand,
    DeleteCommand,
    DeleteProfileCommand,
    HelpCommand,
    Ignore,
    ParsedUpdate,
    PhotoMessage,
    ProfileCommand,
    SummaryCommand,
    ViewContextCommand,
    parse_update,
)
from workflows.build_day_report import build_day_report
from workflows.delete_meal import run_meal_deletion
from workflows.dm_reply import send_dm
from workflows.handle_context_command import handle_add_context, handle_view_context
from workflows.handle_photo import handle_photo
from workflows.handle_profile_command import (
    handle_delete_profile,
    handle_help,
    handle_profile_command,
)
from workflows.send_day_report import send_day_report

logger = logging.getLogger(__name__)

# Launch-time abuse/cost stop-gap: each user gets this many LLM-backed private
# commands (/profile with text, /addcontext) per day. Read-only commands are free.
DAILY_LLM_LIMIT = 25

_LIMIT_REPLY = (
    "You have hit today's limit for AI replies. Try again tomorrow. "
    "Your profile and notes are saved and still work on every photo."
)

# Parsed types that originate in a group chat and stay behind the group allowlist.
_GROUP_TYPES = (PhotoMessage, SummaryCommand, DeleteCommand)


@dataclass(frozen=True, slots=True)
class Dependencies:
    repo: PhotoRepository
    profile_repo: ProfileRepository
    image_estimator: ImageEstimator
    day_summarizer: DaySummarizer
    profile_extractor: ProfileExtractor
    context_rewriter: ContextRewriter
    telegram: TelegramBotApi
    timezone: ZoneInfo
    allowed_chat_ids: tuple[int, ...]


async def dispatch_update(update: dict[str, Any], *, deps: Dependencies) -> None:
    parsed = parse_update(update)
    chat_id = _chat_id_of(parsed)
    if chat_id is None:
        return

    if isinstance(parsed, _GROUP_TYPES):
        # Group surface keeps its default-deny allowlist.
        if deps.allowed_chat_ids and chat_id not in deps.allowed_chat_ids:
            logger.info(
                "ignoring chat_id=%s (allowed=%s)", chat_id, deps.allowed_chat_ids
            )
            return
        logger.info("webhook chat_id=%s", chat_id)
        await _dispatch_group(parsed, chat_id=chat_id, deps=deps)
        return

    # INTENTIONAL BYPASS: private (DM) commands skip the group allowlist. The
    # profile surface is global per person and tied to no group, so gating it on
    # allowed_chat_ids would block every DM. Authenticity for this write surface
    # comes from the required Telegram webhook secret (see api/lifespan.py), not
    # the allowlist. Do not "restore" an allowlist check here.
    logger.info(
        "dm received chat=%s command=%s text=%r",
        chat_id,
        type(parsed).__name__,
        _command_text(parsed),
    )
    await _dispatch_private(parsed, deps=deps)


async def _dispatch_group(
    parsed: ParsedUpdate,
    *,
    chat_id: int,
    deps: Dependencies,
) -> None:
    match parsed:
        case PhotoMessage(photo=photo):
            await handle_photo(
                photo,
                repo=deps.repo,
                profile_repo=deps.profile_repo,
                image_estimator=deps.image_estimator,
                telegram=deps.telegram,
                timezone=deps.timezone,
            )

        case DeleteCommand(
            target_message_id=target_message_id,
            requester_sender_id=requester_sender_id,
        ):
            if requester_sender_id is None:
                return
            owner_id = await deps.repo.meal_owner_id(
                chat_id=chat_id, message_id=target_message_id
            )
            if owner_id != requester_sender_id:
                logger.info(
                    "ignoring /delete chat=%s msg=%s requester=%s owner=%s",
                    chat_id,
                    target_message_id,
                    requester_sender_id,
                    owner_id,
                )
                return
            await run_meal_deletion(
                repo=deps.repo,
                telegram=deps.telegram,
                timezone=deps.timezone,
                chat_id=chat_id,
                message_id=target_message_id,
            )

        case SummaryCommand():
            report = await build_day_report(
                repo=deps.repo,
                profile_repo=deps.profile_repo,
                day_summarizer=deps.day_summarizer,
                chat_id=chat_id,
                day_iso=None,
                timezone=deps.timezone,
            )
            await send_day_report(telegram=deps.telegram, report=report)


async def _dispatch_private(parsed: ParsedUpdate, *, deps: Dependencies) -> None:
    match parsed:
        case ProfileCommand() as command:
            # Viewing (no text) is free; setting calls the extractor, so it is capped.
            if command.text and not await _allow_llm_command(
                deps, command.user_id, command.chat_id
            ):
                return
            await handle_profile_command(
                command,
                repo=deps.profile_repo,
                extractor=deps.profile_extractor,
                telegram=deps.telegram,
            )

        case AddContextCommand() as command:
            # The AI rewrite runs on every add, so this is a capped LLM command.
            if not await _allow_llm_command(deps, command.user_id, command.chat_id):
                return
            await handle_add_context(
                command,
                repo=deps.profile_repo,
                rewriter=deps.context_rewriter,
                telegram=deps.telegram,
            )

        case ViewContextCommand() as command:
            await handle_view_context(
                command, repo=deps.profile_repo, telegram=deps.telegram
            )

        case DeleteProfileCommand() as command:
            await handle_delete_profile(
                command, repo=deps.profile_repo, telegram=deps.telegram
            )

        case HelpCommand() as command:
            await handle_help(command, telegram=deps.telegram)


async def _allow_llm_command(
    deps: Dependencies,
    user_id: int,
    chat_id: int,
) -> bool:
    """Count one LLM-backed command against the daily cap; reply and bail if over."""
    day_key = today_day_key(deps.timezone)
    count = await deps.profile_repo.bump_daily_llm_count(user_id, day_key)
    logger.info(
        "dm rate-cap user=%s day=%s count=%s/%s",
        user_id,
        day_key,
        count,
        DAILY_LLM_LIMIT,
    )
    if count > DAILY_LLM_LIMIT:
        logger.info("dm rate-cap hit user=%s, replying with limit notice", user_id)
        await send_dm(deps.telegram, chat_id, _LIMIT_REPLY)
        return False
    return True


def _command_text(parsed: ParsedUpdate) -> str:
    """The user-typed argument for a private command, for the received-log."""
    match parsed:
        case ProfileCommand(text=text) | AddContextCommand(text=text):
            return text
        case _:
            return ""


def _chat_id_of(parsed: ParsedUpdate) -> int | None:
    match parsed:
        case PhotoMessage(photo=photo):
            return photo.chat_id
        case SummaryCommand(chat_id=chat_id) | DeleteCommand(chat_id=chat_id):
            return chat_id
        case (
            ProfileCommand(chat_id=chat_id)
            | AddContextCommand(chat_id=chat_id)
            | ViewContextCommand(chat_id=chat_id)
            | DeleteProfileCommand(chat_id=chat_id)
            | HelpCommand(chat_id=chat_id)
        ):
            return chat_id
        case Ignore():
            return None
