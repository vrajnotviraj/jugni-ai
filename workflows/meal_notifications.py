import logging

from presenters.meal_deleted import MEAL_DELETED_PARSE_MODE, format_meal_deleted
from presenters.meal_updated import MEAL_UPDATED_PARSE_MODE, format_meal_updated
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)


async def notify_meal_deleted(
    *,
    telegram: TelegramBotApi,
    chat_id: int,
    sender_label: str,
    dish: str,
    calories: int,
    new_total_calories: int,
    day_key: str,
    today_key: str,
) -> bool:
    text = format_meal_deleted(
        sender_label=sender_label,
        dish=dish,
        calories=calories,
        new_total_calories=new_total_calories,
        day_key=day_key,
        today_key=today_key,
    )
    try:
        await telegram.send_message(chat_id, text, parse_mode=MEAL_DELETED_PARSE_MODE)
    except Exception:
        logger.exception(
            "Failed to send meal-deleted notice chat=%s sender=%s",
            chat_id,
            sender_label,
        )
        return False
    return True


async def notify_meal_updated(
    *,
    telegram: TelegramBotApi,
    chat_id: int,
    sender_label: str,
    dish: str,
    previous_calories: int,
    new_calories: int,
    new_total_calories: int,
    day_key: str,
    today_key: str,
) -> bool:
    text = format_meal_updated(
        sender_label=sender_label,
        dish=dish,
        previous_calories=previous_calories,
        new_calories=new_calories,
        new_total_calories=new_total_calories,
        day_key=day_key,
        today_key=today_key,
    )
    try:
        await telegram.send_message(chat_id, text, parse_mode=MEAL_UPDATED_PARSE_MODE)
    except Exception:
        logger.exception(
            "Failed to send meal-updated notice chat=%s sender=%s",
            chat_id,
            sender_label,
        )
        return False
    return True
