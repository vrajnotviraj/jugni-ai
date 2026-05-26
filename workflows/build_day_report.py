import asyncio
import logging
from zoneinfo import ZoneInfo

from analyzers.summary.factory import DaySummarizer
from core.dates import day_key_for_day_iso, today_day_key
from domain.breakdown import daily_user_breakdown
from domain.day import DayNote, DayReport
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
        *(day_summarizer(list(user.meals)) for user in users)
    )
    notes_list = list(notes)

    calibrated_notes = await _calibrate_scores(day_summarizer, users, notes_list)

    return DayReport.assemble(
        chat_id,
        day_key,
        users,
        calibrated_notes,
        total_photos=len(photos),
    )


async def _calibrate_scores(
    day_summarizer: DaySummarizer,
    users,
    notes: list[DayNote],
) -> list[DayNote]:
    if len(users) < 2:
        return notes

    rerank_input = [
        (user.sender_label, list(user.meals), note)
        for user, note in zip(users, notes, strict=True)
    ]
    score_by_label = await day_summarizer.rerank(rerank_input)

    return [
        DayNote(
            summary=note.summary,
            health_score=score_by_label.get(user.sender_label, note.health_score),
        )
        for user, note in zip(users, notes, strict=True)
    ]
