import asyncio
import logging
from zoneinfo import ZoneInfo

from analyzers.summary.factory import DaySummarizer
from core.dates import day_key_for_day_iso, summary_time_context, today_day_key
from domain.breakdown import daily_user_breakdown
from domain.day import DayReport
from storage.photo_repository import PhotoRepository

logger = logging.getLogger(__name__)


async def build_day_report(
    *,
    repo: PhotoRepository,
    day_summarizer: DaySummarizer,
    chat_id: int,
    day_iso: str | None,
    timezone: ZoneInfo,
) -> DayReport:
    day_key = day_key_for_day_iso(day_iso) if day_iso else today_day_key(timezone)
    time_context = summary_time_context(day_key, timezone)
    photos = await repo.estimated_photos_for_day(chat_id=chat_id, day_key=day_key)
    users = daily_user_breakdown(photos, timezone=timezone)
    logger.info(
        "summary chat=%s day=%s photos=%s users=%s",
        chat_id,
        day_key,
        len(photos),
        len(users),
    )

    notes = await asyncio.gather(
        *(day_summarizer(list(user.meals), as_of=time_context) for user in users)
    )

    return DayReport.assemble(
        chat_id,
        day_key,
        users,
        list(notes),
        total_photos=len(photos),
    )
