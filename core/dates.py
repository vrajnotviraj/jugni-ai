from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_day_key(timezone: ZoneInfo, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone)
    return current.astimezone(timezone).date().isoformat()


def day_key_for_day_iso(day_iso: str) -> str:
    return date.fromisoformat(day_iso).isoformat()


def day_key_for_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).date().isoformat()
