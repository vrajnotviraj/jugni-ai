from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.dependencies import (
    admin_secret_header,
    get_day_summarizer,
    get_repo,
    get_settings,
    get_telegram,
    resolve_target_chat_id,
    verify_admin_secret,
)
from controllers.build_day_report import build_day_report
from controllers.send_day_report import send_day_report
from core.settings import Settings
from storage.photo_repository import PhotoRepository
from summary_analyser.factory import DaySummarizer
from telegram.api import TelegramBotApi

router = APIRouter()


@router.get("/api/summary")
async def get_day_summary(
    date: str | None = Query(
        default=None,
        description="Local-day ISO date, defaults to today.",
    ),
    chat_id: int | None = Query(default=None),
    send: bool = Query(default=False, description="Also send the summary to Telegram."),
    settings: Settings = Depends(get_settings),
    repo: PhotoRepository = Depends(get_repo),
    day_summarizer: DaySummarizer = Depends(get_day_summarizer),
    telegram: TelegramBotApi = Depends(get_telegram),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    target_chat_id = resolve_target_chat_id(settings, chat_id)

    report = await build_day_report(
        repo=repo,
        day_summarizer=day_summarizer,
        chat_id=target_chat_id,
        day_iso=date,
        timezone=settings.timezone,
    )

    if send:
        await send_day_report(telegram=telegram, report=report)

    return {
        "ok": True,
        "chat_id": report.chat_id,
        "day": report.day_key,
        "total_photos": report.total_photos,
        "users": [asdict(user) for user in report.users],
    }
