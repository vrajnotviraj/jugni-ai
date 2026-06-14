from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# The local hour at which a new eating day begins. Meals logged before it (e.g. a
# 3 AM late-night snack) count toward the previous day, so the morning-after
# summary still reflects what was actually eaten "that night". Bucketing shifts
# the clock back by this many hours before taking the calendar date.
DAY_START_HOUR = 4


def today_day_key(timezone: ZoneInfo, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone)
    return day_key_for_datetime(current, timezone)


def recent_day_keys(as_of: str, count: int) -> list[str]:
    """The ``count`` ISO day-keys ending at ``as_of``, most recent first."""
    start = date.fromisoformat(as_of)
    return [(start - timedelta(days=offset)).isoformat() for offset in range(count)]


def day_key_for_day_iso(day_iso: str) -> str:
    return date.fromisoformat(day_iso).isoformat()


def day_key_for_datetime(value: datetime, timezone: ZoneInfo) -> str:
    """The eating-day key for ``value`` in ``timezone``.

    The local clock is shifted back by ``DAY_START_HOUR`` before the date is
    taken, so the late-night tail of a day (00:00 up to ``DAY_START_HOUR``)
    rolls into the previous eating day rather than starting a new one.
    """
    local = value.astimezone(timezone) - timedelta(hours=DAY_START_HOUR)
    return local.date().isoformat()


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

    # Compare against the *eating-day* key (same 4 AM rollover as the day_keys
    # being summarised), not the raw calendar date. Using current.date() would
    # mark the 00:00–DAY_START_HOUR late-night tail as a past day and wrongly
    # report it "OVER" while the eating day is in fact still in progress.
    current_day_key = day_key_for_datetime(current, timezone)
    if day_key < current_day_key or current.hour >= DAY_OVER_HOUR:
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


def meal_period_for_hour(hour: int) -> str:
    """The meal period a given local hour falls into: breakfast, lunch, or
    dinner. Used to tell whether the meal for the current slot has already been
    eaten today (a dinner-window meal means dinner is done)."""
    if hour < LUNCH_FROM_HOUR:
        return "breakfast"
    if hour < DINNER_FROM_HOUR:
        return "lunch"
    return "dinner"


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
