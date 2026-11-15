import logging

from domain.day import DayReport
from presenters.day_summary import (
    SUMMARY_PARSE_MODE,
    format_day_summary_chunks,
    format_day_summary_rich,
)
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)


async def send_day_report(*, telegram: TelegramBotApi, report: DayReport) -> None:
    rich = format_day_summary_rich(report)
    if rich is not None:
        try:
            await telegram.send_rich_message(report.chat_id, rich)
            return
        except Exception:
            logger.exception(
                "rich day summary failed chat=%s — sending classic", report.chat_id
            )
    for chunk in format_day_summary_chunks(report):
        await telegram.send_message(
            report.chat_id,
            chunk,
            parse_mode=SUMMARY_PARSE_MODE,
        )
