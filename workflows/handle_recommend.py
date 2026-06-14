"""Orchestrate /recommend on both surfaces.

Every command — bare or with text — produces a macro-aware suggestion. A bare
``/recommend`` plans the meal for the current time of day (or a round-off snack
if that meal is already logged); any text refines it with an explicit slot or a
free-form ask. There is no meal-type menu: one command, one suggestion.
"""

import logging
import re
from zoneinfo import ZoneInfo

from analyzers.recommend.recommender import Recommender
from domain.recommendation import MEAL_SLOTS
from presenters.recommend_reply import (
    RECOMMEND_LINK_PREVIEW,
    RECOMMEND_REPLY_PARSE_MODE,
    format_recommendation,
)
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import RecommendCommand
from workflows.build_recommendation_context import build_recommendation_context

logger = logging.getLogger(__name__)

GENERATING_REPLY = "🍽 Generating your recommendation…"


async def handle_recommend_command(
    command: RecommendCommand,
    *,
    repo: PhotoRepository,
    profile_repo: ProfileRepository,
    recommender: Recommender,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    allowed_chat_ids: tuple[int, ...],
) -> None:
    is_group = command.surface == "group"
    # Replying to the command threads the conversation in groups.
    reply_to = command.message_id if is_group else None

    # Acknowledge immediately, then edit this same message into the finished
    # card once the suggestion (and its recipe videos) return — so the chat
    # shows progress instead of silence during the LLM and YouTube calls.
    placeholder_id = await _send_placeholder(telegram, command.chat_id, reply_to)

    slot = parse_slot(command.text)
    # Meal history lives in the group chat: the command's own chat on the
    # group surface, the first allowed group for a DM (KTD7). No allowed
    # group means a profile-only recommendation.
    if is_group:
        history_chat_id = command.chat_id
    else:
        history_chat_id = allowed_chat_ids[0] if allowed_chat_ids else None

    context = await build_recommendation_context(
        user_id=command.user_id,
        sender_label=command.sender_label,
        surface=command.surface,
        slot=slot,
        user_request=command.text.strip(),
        repo=repo,
        profile_repo=profile_repo,
        chat_id=history_chat_id,
        timezone=timezone,
    )
    result = await recommender(context)
    await _deliver(
        telegram,
        command.chat_id,
        format_recommendation(
            result, for_label=command.sender_label if is_group else ""
        ),
        placeholder_id=placeholder_id,
        reply_to_message_id=reply_to,
    )


def parse_slot(text: str) -> str | None:
    """The slot keyword from free text; the raw text itself goes to the prompt.

    Whole-word match (plural allowed) so "brunch" or "lunchbox" never reads
    as an explicit lunch ask."""
    lowered = text.casefold()
    return next((s for s in MEAL_SLOTS if re.search(rf"\b{s}s?\b", lowered)), None)


async def _send_placeholder(
    telegram: TelegramBotApi,
    chat_id: int,
    reply_to_message_id: int | None,
) -> int | None:
    # Best-effort: if the ack fails we just fall back to sending the card fresh.
    try:
        return await telegram.send_message(
            chat_id=chat_id,
            text=GENERATING_REPLY,
            reply_to_message_id=reply_to_message_id,
        )
    except Exception:
        logger.exception("recommend placeholder send failed chat=%s", chat_id)
        return None


async def _deliver(
    telegram: TelegramBotApi,
    chat_id: int,
    text: str,
    *,
    placeholder_id: int | None,
    reply_to_message_id: int | None = None,
) -> None:
    """Show the finished card: edit the placeholder in place, or send fresh when
    there was no placeholder or the edit fails."""
    if placeholder_id is not None:
        try:
            await telegram.edit_message_text(
                chat_id=chat_id,
                message_id=placeholder_id,
                text=text,
                parse_mode=RECOMMEND_REPLY_PARSE_MODE,
                link_preview_options=RECOMMEND_LINK_PREVIEW,
            )
            return
        except Exception:
            # Stale or deleted placeholder; fall back to a fresh card so the
            # reply is never silently dropped.
            logger.exception(
                "recommend placeholder edit failed chat=%s — sending fresh", chat_id
            )

    try:
        await telegram.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            parse_mode=RECOMMEND_REPLY_PARSE_MODE,
            link_preview_options=RECOMMEND_LINK_PREVIEW,
        )
    except Exception:
        logger.exception("recommend reply failed chat=%s", chat_id)
