from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from domain.day import Meal, UserDay
from domain.photo import StoredPhoto


def daily_user_breakdown(
    photos: list[StoredPhoto],
    *,
    timezone: ZoneInfo,
    zones: dict[str, ZoneInfo] | None = None,
) -> list[UserDay]:
    # Each meal's time is shown in its sender's own timezone when known, so the
    # summary reads in the clock they actually ate by; ``timezone`` (the app
    # default) is the fallback for senders without a resolved zone.
    zones = zones or {}
    # Keep each meal paired with its original instant so meals can be ordered
    # chronologically below. The "%H:%M" eaten_at label cannot be sorted on: with
    # the 4 AM day rollover a late-night meal ("02:00") would otherwise sort
    # before an evening one ("22:00") that actually happened earlier.
    accumulator: dict[str, list[tuple[datetime | None, Meal]]] = {}
    calories: dict[str, int] = {}
    order: list[str] = []

    for photo in photos:
        meal = Meal(
            dish=photo.dish.strip(),
            calories=photo.calories,
            eaten_at=_format_local_time(
                photo.sent_at, zones.get(photo.sender_label, timezone)
            ),
            protein_g=photo.protein_g,
            carb_g=photo.carb_g,
            fat_g=photo.fat_g,
            fibre_g=photo.fibre_g,
            added_sugar_g=photo.added_sugar_g,
            sat_fat_g=photo.sat_fat_g,
        )
        if photo.sender_label not in accumulator:
            accumulator[photo.sender_label] = []
            calories[photo.sender_label] = 0
            order.append(photo.sender_label)
        accumulator[photo.sender_label].append((photo.sent_at, meal))
        calories[photo.sender_label] += photo.calories

    users: list[UserDay] = []
    for sender_label in order:
        ordered = sorted(
            accumulator[sender_label],
            key=lambda item: item[0] or datetime.min.replace(tzinfo=UTC),
        )
        meals = [meal for _, meal in ordered]
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
