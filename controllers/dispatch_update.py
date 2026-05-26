import logging
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from controllers.build_day_report import build_day_report
from controllers.delete_meal import delete_meal_for_sender
from controllers.handle_photo import handle_photo
from controllers.send_day_report import send_day_report
from image_analyser.factory import ImageEstimator
from storage.photo_repository import PhotoRepository
from summary_analyser.factory import DaySummarizer
from telegram.api import TelegramBotApi
from telegram.updates import (
    DeleteCommand,
    Ignore,
    PhotoMessage,
    SummaryCommand,
    parse_update,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Dependencies:
    repo: PhotoRepository
    image_estimator: ImageEstimator
    day_summarizer: DaySummarizer
    telegram: TelegramBotApi
    timezone: ZoneInfo
    configured_group_chat_id: int | None


async def dispatch_update(update: dict[str, Any], *, deps: Dependencies) -> None:
    parsed = parse_update(update)

    match parsed:
        case PhotoMessage(photo=photo):
            if not _chat_is_allowed(photo.chat_id, deps.configured_group_chat_id):
                logger.info(
                    "ignoring update chat_id=%s (configured group is %s)",
                    photo.chat_id,
                    deps.configured_group_chat_id,
                )
                return
            logger.info("webhook chat_id=%s", photo.chat_id)
            await handle_photo(
                photo,
                repo=deps.repo,
                image_estimator=deps.image_estimator,
                telegram=deps.telegram,
            )

        case DeleteCommand(
            chat_id=chat_id,
            target_message_id=target_message_id,
            requester_sender_id=requester_sender_id,
        ):
            if not _chat_is_allowed(chat_id, deps.configured_group_chat_id):
                logger.info(
                    "ignoring chat_id=%s (configured group is %s)",
                    chat_id,
                    deps.configured_group_chat_id,
                )
                return
            logger.info(
                "webhook /delete chat=%s msg=%s requester=%s",
                chat_id,
                target_message_id,
                requester_sender_id,
            )
            await delete_meal_for_sender(
                repo=deps.repo,
                telegram=deps.telegram,
                timezone=deps.timezone,
                chat_id=chat_id,
                target_message_id=target_message_id,
                requester_sender_id=requester_sender_id,
            )

        case SummaryCommand(chat_id=chat_id):
            if not _chat_is_allowed(chat_id, deps.configured_group_chat_id):
                logger.info(
                    "ignoring chat_id=%s (configured group is %s)",
                    chat_id,
                    deps.configured_group_chat_id,
                )
                return
            logger.info("webhook chat_id=%s", chat_id)
            report = await build_day_report(
                repo=deps.repo,
                day_summarizer=deps.day_summarizer,
                chat_id=chat_id,
                day_iso=None,
                timezone=deps.timezone,
            )
            await send_day_report(telegram=deps.telegram, report=report)

        case Ignore():
            return


def _chat_is_allowed(chat_id: int, configured: int | None) -> bool:
    if configured is None:
        return True
    return chat_id == configured
