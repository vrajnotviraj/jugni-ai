from domain.day import DayReport
from presenters.day_summary import SUMMARY_PARSE_MODE, format_day_summary_chunks
from telegram.api import TelegramBotApi


async def send_day_report(*, telegram: TelegramBotApi, report: DayReport) -> None:
    for chunk in format_day_summary_chunks(report):
        await telegram.send_message(
            report.chat_id,
            chunk,
            parse_mode=SUMMARY_PARSE_MODE,
        )
