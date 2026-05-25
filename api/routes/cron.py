import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import (
    get_day_summarizer,
    get_repo,
    get_settings,
    get_telegram,
    resolve_target_chat_id,
)
from controllers.build_day_report import build_day_report
from controllers.send_day_report import send_day_report
from core.settings import Settings
from storage.photo_repository import PhotoRepository
from summary_analyser.factory import DaySummarizer
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_cron_secret(settings: Settings, authorization: str | None) -> None:
    if not settings.cron_secret:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET is not configured on the server.",
        )
    expected = f"Bearer {settings.cron_secret}"
    if authorization and hmac.compare_digest(authorization, expected):
        return
    raise HTTPException(status_code=401, detail="Invalid cron secret.")


@router.get("/api/cron/daily-summary")
async def daily_summary_cron(
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    day_summarizer: DaySummarizer = Depends(get_day_summarizer),
    telegram: TelegramBotApi = Depends(get_telegram),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    _verify_cron_secret(settings, authorization)
    target_chat_id = resolve_target_chat_id(settings, None)

    report = await build_day_report(
        repo=repo,
        day_summarizer=day_summarizer,
        chat_id=target_chat_id,
        day_iso=None,
        timezone=settings.timezone,
    )
    await send_day_report(telegram=telegram, report=report)

    logger.info(
        "cron daily-summary sent chat=%s day=%s photos=%s users=%s",
        report.chat_id,
        report.day_key,
        report.total_photos,
        len(report.users),
    )

    return {
        "ok": True,
        "chat_id": report.chat_id,
        "day": report.day_key,
        "total_photos": report.total_photos,
        "users": len(report.users),
    }
