import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import (
    get_repo,
    get_settings,
    get_telegram,
    verify_cron_secret,
)
from core.settings import Settings
from presenters.streak_nudge import STREAK_NUDGE_PARSE_MODE, format_streak_nudge
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi
from workflows.streak_nudge import build_streak_nudge

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/cron/streak-nudge")
async def streak_nudge_cron(
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    telegram: TelegramBotApi = Depends(get_telegram),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    verify_cron_secret(settings, authorization)

    if not settings.telegram_group_chat_ids:
        raise HTTPException(
            status_code=500, detail="TELEGRAM_GROUP_CHAT_ID is not configured."
        )

    nudged: list[int] = []
    for chat_id in settings.telegram_group_chat_ids:
        at_risk = await build_streak_nudge(
            repo=repo, chat_id=chat_id, timezone=settings.timezone
        )
        if not at_risk:
            continue
        await telegram.send_message(
            chat_id,
            format_streak_nudge(at_risk),
            parse_mode=STREAK_NUDGE_PARSE_MODE,
        )
        logger.info("cron streak-nudge sent chat=%s at_risk=%s", chat_id, len(at_risk))
        nudged.append(chat_id)

    return {"ok": True, "chat_ids": nudged}
