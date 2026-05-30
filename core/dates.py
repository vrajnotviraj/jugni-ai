from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_day_key(timezone: ZoneInfo, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone)
    return current.astimezone(timezone).date().isoformat()


def day_key_for_day_iso(day_iso: str) -> str:
    return date.fromisoformat(day_iso).isoformat()


def day_key_for_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).date().isoformat()


# Meal-period boundaries by local hour, shared by the day-over judgment and the
# next-meal inference so both speak the same clock. Breakfast runs before
# LUNCH_FROM_HOUR, lunch from LUNCH_FROM_HOUR, dinner from DINNER_FROM_HOUR; at
# and after DAY_OVER_HOUR the eating day is treated as finished.
LUNCH_FROM_HOUR = 11
DINNER_FROM_HOUR = 17
DAY_OVER_HOUR = 21


def summary_time_context(
    day_key: str,
    timezone: ZoneInfo,
    now: datetime | None = None,
) -> str:
    current = (now or datetime.now(timezone)).astimezone(timezone)

    if day_key < current.date().isoformat() or current.hour >= DAY_OVER_HOUR:
        return (
            "The eating day is OVER; analyse it as a finished day with all three "
            "meal periods passed. Do not suggest eating now or a next meal for today."
        )
    return (
        f"It is now {current.strftime('%H:%M')} and the day is still IN PROGRESS. "
        f"Only meal periods before now have happened (breakfast before "
        f"{LUNCH_FROM_HOUR:02d}:00, lunch from {LUNCH_FROM_HOUR:02d}:00, dinner "
        f"from {DINNER_FROM_HOUR:02d}:00); later periods are not yet expected."
    )


def next_meal_slot(timezone: ZoneInfo, now: datetime | None = None) -> str:
    """The next meal to plan for, by the local hour in ``timezone``.

    Returns breakfast, lunch, or dinner during the day; once the eating day is
    over (>= DAY_OVER_HOUR) it points at tomorrow's breakfast. ``snack`` is never
    auto-inferred; it is only ever an explicit user choice.
    """
    hour = (now or datetime.now(timezone)).astimezone(timezone).hour
    if hour < LUNCH_FROM_HOUR or hour >= DAY_OVER_HOUR:
        return "breakfast"
    if hour < DINNER_FROM_HOUR:
        return "lunch"
    return "dinner"
