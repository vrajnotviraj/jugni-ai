from datetime import datetime
from zoneinfo import ZoneInfo

from domain.day import Meal, UserDay
from domain.photo import StoredPhoto


def daily_user_breakdown(
    photos: list[StoredPhoto],
    *,
    timezone: ZoneInfo,
) -> list[UserDay]:
    accumulator: dict[str, list[Meal]] = {}
    calories: dict[str, int] = {}
    order: list[str] = []

    for photo in photos:
        meal = Meal(
            dish=photo.dish.strip(),
            calories=photo.calories,
            eaten_at=_format_local_time(photo.sent_at, timezone),
        )
        if photo.sender_label not in accumulator:
            accumulator[photo.sender_label] = []
            calories[photo.sender_label] = 0
            order.append(photo.sender_label)
        accumulator[photo.sender_label].append(meal)
        calories[photo.sender_label] += photo.calories

    users: list[UserDay] = []
    for sender_label in order:
        meals = sorted(accumulator[sender_label], key=lambda m: m.eaten_at or "")
        users.append(
            UserDay(
                sender_label=sender_label,
                calories=calories[sender_label],
                meals=tuple(meals),
            )
        )
    return users


def _format_local_time(value: datetime | None, timezone: ZoneInfo) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone).strftime("%H:%M")
