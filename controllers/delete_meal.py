import logging
from zoneinfo import ZoneInfo

from core.dates import today_day_key
from presenters.meal_deleted import MEAL_DELETED_PARSE_MODE, format_meal_deleted
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)


async def delete_meal_for_sender(
    *,
    repo: PhotoRepository,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    chat_id: int,
    target_message_id: int,
    requester_sender_id: int | None,
) -> None:
    if requester_sender_id is None:
        return

    deleted = await repo.delete_meal(
        chat_id=chat_id,
        message_id=target_message_id,
        expected_sender_id=requester_sender_id,
    )
    if deleted is None:
        logger.info(
            "ignoring /delete chat=%s msg=%s requester=%s (missing or not owner)",
            chat_id,
            target_message_id,
            requester_sender_id,
        )
        return

    new_total = await repo.daily_user_calories(
        chat_id=chat_id,
        day_key=deleted.day_key,
        sender_label=deleted.sender_label,
    )

    text = format_meal_deleted(
        sender_label=deleted.sender_label,
        dish=deleted.dish,
        calories=deleted.calories,
        new_total_calories=new_total,
        day_key=deleted.day_key,
        today_key=today_day_key(timezone),
    )
    try:
        await telegram.send_message(chat_id, text, parse_mode=MEAL_DELETED_PARSE_MODE)
    except Exception:
        logger.exception(
            "Failed to send meal-deleted notice chat=%s sender=%s",
            chat_id,
            deleted.sender_label,
        )
