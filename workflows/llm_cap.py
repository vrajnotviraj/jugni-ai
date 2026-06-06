"""The per-user daily LLM cap, shared by every LLM-backed command.

Launch-time abuse/cost stop-gap: each user gets DAILY_LLM_LIMIT LLM-backed
commands per day, charged wherever the LLM call actually happens (dispatch
time for one-step commands, press time for keyboard callbacks). Read-only
commands are free.
"""

import logging
from zoneinfo import ZoneInfo

from core.dates import today_day_key
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from workflows.dm_reply import send_dm

logger = logging.getLogger(__name__)

DAILY_LLM_LIMIT = 25

_LIMIT_REPLY = (
    "You have hit today's limit for AI replies. Try again tomorrow. "
    "Your profile and notes are saved and still work on every photo."
)


async def allow_llm_command(
    *,
    profile_repo: ProfileRepository,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    user_id: int,
    chat_id: int,
) -> bool:
    """Count one LLM-backed command against the daily cap; reply and bail if over."""
    day_key = today_day_key(timezone)
    count = await profile_repo.bump_daily_llm_count(user_id, day_key)
    logger.info(
        "llm rate-cap user=%s day=%s count=%s/%s",
        user_id,
        day_key,
        count,
        DAILY_LLM_LIMIT,
    )
    if count > DAILY_LLM_LIMIT:
        logger.info("llm rate-cap hit user=%s, replying with limit notice", user_id)
        await send_dm(telegram, chat_id, _LIMIT_REPLY)
        return False
    return True
