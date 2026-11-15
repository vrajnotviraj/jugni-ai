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
    format_recommendation,
    recommend_link_preview,
)
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.updates import RecommendCommand
from workflows.build_recommendation_context import build_recommendation_context
from workflows.loading_reply import Reply, finish_loading, start_loading

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

    placeholder_id = await start_loading(
        telegram, command.chat_id, reply_to, GENERATING_REPLY
    )

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
    # Classic HTML on purpose: rich messages carry no link preview, and the
    # first recipe's video preview is part of this card.
    reply = Reply(
        format_recommendation(
            result, for_label=command.sender_label if is_group else ""
        ),
        link_preview_options=recommend_link_preview(result),
    )
    await finish_loading(telegram, command.chat_id, reply_to, placeholder_id, reply)


def parse_slot(text: str) -> str | None:
    """The slot keyword from free text; the raw text itself goes to the prompt.

    Whole-word match (plural allowed) so "brunch" or "lunchbox" never reads
    as an explicit lunch ask."""
    lowered = text.casefold()
    return next((s for s in MEAL_SLOTS if re.search(rf"\b{s}s?\b", lowered)), None)
