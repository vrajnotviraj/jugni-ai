import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from analyzers.summary.factory import DaySummarizer
from api.dependencies import (
    get_day_summarizer,
    get_profile_repo,
    get_repo,
    get_settings,
    get_telegram,
    verify_cron_secret,
)
from core.settings import Settings
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from workflows.build_day_report import build_day_report
from workflows.send_day_report import send_day_report

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/cron/daily-summary")
async def daily_summary_cron(
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    profile_repo: ProfileRepository = Depends(get_profile_repo),
    day_summarizer: DaySummarizer = Depends(get_day_summarizer),
    telegram: TelegramBotApi = Depends(get_telegram),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    verify_cron_secret(settings, authorization)

    if not settings.telegram_group_chat_ids:
        raise HTTPException(
            status_code=500, detail="TELEGRAM_GROUP_CHAT_ID is not configured."
        )

    sent: list[int] = []
    for chat_id in settings.telegram_group_chat_ids:
        report = await build_day_report(
            repo=repo,
            profile_repo=profile_repo,
            day_summarizer=day_summarizer,
            chat_id=chat_id,
            day_iso=None,
            timezone=settings.timezone,
        )
        await send_day_report(telegram=telegram, report=report)
        logger.info(
            "cron daily-summary sent chat=%s day=%s", report.chat_id, report.day_key
        )
        sent.append(report.chat_id)

    return {"ok": True, "chat_ids": sent}
