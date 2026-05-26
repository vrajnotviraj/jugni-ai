import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from core.dates import today_day_key
from domain.photo import DeletedMeal
from storage.photo_repository import PhotoRepository
from telegram.api import TelegramBotApi
from workflows.meal_notifications import notify_meal_deleted

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MealDeletionResult:
    deleted: DeletedMeal
    new_total_calories: int
    notified: bool


async def run_meal_deletion(
    *,
    repo: PhotoRepository,
    telegram: TelegramBotApi,
    timezone: ZoneInfo,
    chat_id: int,
    message_id: int,
    notify: bool = True,
) -> MealDeletionResult | None:
    deleted = await repo.delete_meal(chat_id=chat_id, message_id=message_id)
    if deleted is None:
        return None

    new_total = await repo.daily_user_calories(
        chat_id=chat_id,
        day_key=deleted.day_key,
        sender_label=deleted.sender_label,
    )

    notified = False
    if notify:
        notified = await notify_meal_deleted(
            telegram=telegram,
            chat_id=chat_id,
            sender_label=deleted.sender_label,
            dish=deleted.dish,
            calories=deleted.calories,
            new_total_calories=new_total,
            day_key=deleted.day_key,
            today_key=today_day_key(timezone),
        )

    return MealDeletionResult(
        deleted=deleted,
        new_total_calories=new_total,
        notified=notified,
    )
