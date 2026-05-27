from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_day_key(timezone: ZoneInfo, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone)
    return current.astimezone(timezone).date().isoformat()


def day_key_for_day_iso(day_iso: str) -> str:
    return date.fromisoformat(day_iso).isoformat()


def day_key_for_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).date().isoformat()


# Hour (local) at and after which the eating day is treated as finished, so the
# summary stops giving "next meal" advice and analyses the day as complete.
_DAY_OVER_HOUR = 21


def summary_time_context(
    day_key: str,
    timezone: ZoneInfo,
    now: datetime | None = None,
) -> str:
    current = (now or datetime.now(timezone)).astimezone(timezone)

    if day_key < current.date().isoformat() or current.hour >= _DAY_OVER_HOUR:
        return (
            "The eating day is OVER; analyse it as a finished day with all three "
            "meal periods passed. Do not suggest eating now or a next meal for today."
        )
    return (
        f"It is now {current.strftime('%H:%M')} and the day is still IN PROGRESS. "
        "Only meal periods before now have happened (breakfast before 11:00, lunch "
        "from 11:00, dinner from 17:00); later periods are not yet expected."
    )
