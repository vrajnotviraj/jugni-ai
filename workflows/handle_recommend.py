"""Orchestrate /recommend on both surfaces.

A bare command (a menu tap auto-sends with no args) gets the slot reply
keyboard — free, no LLM work; tapping a button sends "/recommend <slot>" as a
normal message from whoever tapped, which lands right back here as a one-step
command, charged to that person's own daily cap at dispatch. No callback
handling, no per-button identity: every tap is just a regular command from
its sender.
"""

import logging
from zoneinfo import ZoneInfo

from analyzers.recommend.recommender import Recommender
from domain.recommendation import MEAL_SLOTS
from presenters.recommend_reply import (
    PICK_SLOT_TEXT,
    RECOMMEND_REPLY_PARSE_MODE,
    SLOT_KEYBOARD,
    format_recommendation,
)
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import RecommendCommand
from workflows.build_recommendation_context import build_recommendation_context

logger = logging.getLogger(__name__)

_MODIFIERS = ("high protein", "light")


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
    # Replying to the command threads the conversation in groups and lets the
    # keyboard's ``selective`` flag scope it to the requester.
    reply_to = command.message_id if is_group else None

    if not command.text.strip():
        await _safely_send(
            telegram,
            command.chat_id,
            PICK_SLOT_TEXT,
            reply_to_message_id=reply_to,
            reply_markup=SLOT_KEYBOARD,
        )
        return

    slot, modifier = parse_request_text(command.text)
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
        modifier=modifier,
        user_request=command.text.strip(),
        repo=repo,
        profile_repo=profile_repo,
        chat_id=history_chat_id,
        timezone=timezone,
    )
    result = await recommender(context)
    await _safely_send(
        telegram,
        command.chat_id,
        format_recommendation(
            result, for_label=command.sender_label if is_group else ""
        ),
        reply_to_message_id=reply_to,
    )


def parse_request_text(text: str) -> tuple[str | None, str | None]:
    """Slot and modifier keywords from free text; raw text goes to the prompt."""
    lowered = text.casefold()
    slot = next((s for s in MEAL_SLOTS if s in lowered), None)
    modifier = next((m for m in _MODIFIERS if m in lowered), None)
    return slot, modifier


async def _safely_send(
    telegram: TelegramBotApi,
    chat_id: int,
    text: str,
    *,
    reply_to_message_id: int | None = None,
    reply_markup: dict | None = None,
) -> None:
    try:
        await telegram.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            parse_mode=RECOMMEND_REPLY_PARSE_MODE,
            reply_markup=reply_markup,
        )
    except Exception:
        logger.exception("recommend reply failed chat=%s", chat_id)
