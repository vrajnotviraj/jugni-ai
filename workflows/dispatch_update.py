import logging
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from analyzers.image.factory import ImageEstimator
from analyzers.summary.factory import DaySummarizer
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi
from telegram.updates import (
    DeleteCommand,
    Ignore,
    PhotoMessage,
    SummaryCommand,
    parse_update,
)
from workflows.build_day_report import build_day_report
from workflows.delete_meal import run_meal_deletion
from workflows.handle_photo import handle_photo
from workflows.send_day_report import send_day_report

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Dependencies:
    repo: PhotoRepository
    image_estimator: ImageEstimator
    day_summarizer: DaySummarizer
    telegram: TelegramBotApi
    timezone: ZoneInfo
    allowed_chat_ids: tuple[int, ...]


async def dispatch_update(update: dict[str, Any], *, deps: Dependencies) -> None:
    parsed = parse_update(update)
    chat_id = _chat_id_of(parsed)
    if chat_id is None:
        return
    if deps.allowed_chat_ids and chat_id not in deps.allowed_chat_ids:
        logger.info("ignoring chat_id=%s (allowed=%s)", chat_id, deps.allowed_chat_ids)
        return
    logger.info("webhook chat_id=%s", chat_id)

    match parsed:
        case PhotoMessage(photo=photo):
            await handle_photo(
                photo,
                repo=deps.repo,
                image_estimator=deps.image_estimator,
                telegram=deps.telegram,
                timezone=deps.timezone,
            )

        case DeleteCommand(
            target_message_id=target_message_id,
            requester_sender_id=requester_sender_id,
        ):
            if requester_sender_id is None:
                return
            owner_id = await deps.repo.meal_owner_id(
                chat_id=chat_id, message_id=target_message_id
            )
            if owner_id != requester_sender_id:
                logger.info(
                    "ignoring /delete chat=%s msg=%s requester=%s owner=%s",
                    chat_id,
                    target_message_id,
                    requester_sender_id,
                    owner_id,
                )
                return
            await run_meal_deletion(
                repo=deps.repo,
                telegram=deps.telegram,
                timezone=deps.timezone,
                chat_id=chat_id,
                message_id=target_message_id,
            )

        case SummaryCommand():
            report = await build_day_report(
                repo=deps.repo,
                day_summarizer=deps.day_summarizer,
                chat_id=chat_id,
                day_iso=None,
                timezone=deps.timezone,
            )
            await send_day_report(telegram=deps.telegram, report=report)


def _chat_id_of(parsed: PhotoMessage | SummaryCommand | DeleteCommand | Ignore) -> int | None:
    match parsed:
        case PhotoMessage(photo=photo):
            return photo.chat_id
        case SummaryCommand(chat_id=chat_id) | DeleteCommand(chat_id=chat_id):
            return chat_id
        case Ignore():
            return None
