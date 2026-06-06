"""Orchestrate /recommend: one-step commands, the slot keyboard, and presses.

Cap charging happens here at the LLM call site (KTD5): a one-step command is
charged by dispatch before it reaches this module; the bare-command keyboard
is free; a button press charges the presser's same daily counter before the
LLM call. ``callback_data`` is attacker-controlled (KTD4): the embedded
requester id is ONLY an equality gate, and all context building keys on the
presser's own ``from.id``, so a forged payload can at worst trigger the
presser's own capped recommendation.
"""

import logging
from zoneinfo import ZoneInfo

from analyzers.recommend.recommender import Recommender
from domain.recommendation import MEAL_SLOTS
from presenters.recommend_reply import (
    PICK_SLOT_TEXT,
    RECOMMEND_REPLY_PARSE_MODE,
    format_recommendation,
    slot_keyboard,
)
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import CallbackPressed, RecommendCommand
from workflows.build_recommendation_context import build_recommendation_context
from workflows.llm_cap import allow_llm_command

logger = logging.getLogger(__name__)

_NOT_FOR_YOU = "This one's not for you. Send /recommend to get your own."

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
    # Bare command (a menu tap auto-sends with no args): offer the slot
    # buttons instead of guessing. Free — no LLM work happens here.
    if not command.text.strip():
        await _safely_send(
            telegram,
            command.chat_id,
            PICK_SLOT_TEXT,
            reply_markup=slot_keyboard(command.user_id),
        )
        return

    slot, modifier = parse_request_text(command.text)
    await _recommend_and_reply(
        user_id=command.user_id,
        sender_label=command.sender_label,
        surface=command.surface,
        slot=slot,
        modifier=modifier,
        chat_id=command.chat_id,
        reply_to_message_id=None,
        for_label=command.sender_label if command.surface == "group" else "",
        repo=repo,
        profile_repo=profile_repo,
        recommender=recommender,
        telegram=telegram,
        timezone=timezone,
        allowed_chat_ids=allowed_chat_ids,
    )


async def handle_recommend_callback(
    pressed: CallbackPressed,
    *,
    repo: PhotoRepository,
    profile_repo: ProfileRepository,
    recommender: Recommender,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    allowed_chat_ids: tuple[int, ...],
) -> None:
    parsed = _parse_rec_data(pressed.data)
    if parsed is None:
        # Not our grammar (or malformed/forged data): acknowledge so the
        # client stops spinning, take no action.
        await _safely_answer(telegram, pressed.callback_query_id)
        return
    requester_id, slot = parsed

    # R3: only the original requester's presses are honored. The embedded id
    # is used solely for this equality check, never as a lookup key.
    if pressed.presser_id != requester_id:
        await _safely_answer(
            telegram, pressed.callback_query_id, text=_NOT_FOR_YOU, show_alert=True
        )
        return

    # Telegram requires every press to be answered or clients spin forever.
    await _safely_answer(telegram, pressed.callback_query_id)

    # Charge the presser's own daily counter (same budget as one-step
    # commands) before the LLM call. A double press is just a second capped
    # request — the cap bounds the cost, no idempotency machinery (R4).
    if not await allow_llm_command(
        profile_repo=profile_repo,
        telegram=telegram,
        timezone=timezone,
        user_id=pressed.presser_id,
        chat_id=pressed.chat_id,
    ):
        return

    await _recommend_and_reply(
        user_id=pressed.presser_id,
        sender_label=pressed.presser_label,
        surface="group" if pressed.chat_is_group else "dm",
        slot=slot,
        modifier=None,
        chat_id=pressed.chat_id,
        reply_to_message_id=pressed.message_id,
        for_label=pressed.presser_label if pressed.chat_is_group else "",
        repo=repo,
        profile_repo=profile_repo,
        recommender=recommender,
        telegram=telegram,
        timezone=timezone,
        allowed_chat_ids=allowed_chat_ids,
    )


def parse_request_text(text: str) -> tuple[str | None, str | None]:
    """Slot and modifier keywords from free text; unrecognized words are no
    preference (R1). Public so evals can pin the token grammar."""
    lowered = text.casefold()
    slot = next((s for s in MEAL_SLOTS if s in lowered), None)
    modifier = next((m for m in _MODIFIERS if m in lowered), None)
    return slot, modifier


def _parse_rec_data(data: str) -> tuple[int, str] | None:
    """The rec:<requester_id>:<slot> grammar, None for anything else."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "rec" or parts[2] not in MEAL_SLOTS:
        return None
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        return None


async def _recommend_and_reply(
    *,
    user_id: int,
    sender_label: str,
    surface: str,
    slot: str | None,
    modifier: str | None,
    chat_id: int,
    reply_to_message_id: int | None,
    for_label: str,
    repo: PhotoRepository,
    profile_repo: ProfileRepository,
    recommender: Recommender,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    allowed_chat_ids: tuple[int, ...],
) -> None:
    # Meal history lives in the group chat: the command's own chat on the
    # group surface, the first allowed group for a DM (KTD7). No allowed
    # group means a profile-only recommendation.
    if surface == "group":
        history_chat_id = chat_id
    else:
        history_chat_id = allowed_chat_ids[0] if allowed_chat_ids else None

    context = await build_recommendation_context(
        user_id=user_id,
        sender_label=sender_label,
        surface=surface,
        slot=slot,
        modifier=modifier,
        repo=repo,
        profile_repo=profile_repo,
        chat_id=history_chat_id,
        timezone=timezone,
    )
    result = await recommender(context)
    await _safely_send(
        telegram,
        chat_id,
        format_recommendation(result, for_label=for_label),
        reply_to_message_id=reply_to_message_id,
    )


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


async def _safely_answer(
    telegram: TelegramBotApi,
    callback_query_id: str,
    *,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    # Fire-and-forget by contract: a failed ack must never block the flow.
    try:
        await telegram.answer_callback_query(
            callback_query_id, text=text, show_alert=show_alert
        )
    except Exception:
        logger.exception("answerCallbackQuery failed id=%s", callback_query_id)
