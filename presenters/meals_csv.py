import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from domain.photo import StoredPhoto

CSV_FILENAME_PREFIX = "meals"
CSV_MIME_TYPE = "text/csv"
CSV_COLUMNS = ("date", "sender", "dish", "calories", "eaten_at", "image_link")


def build_meals_csv(
    *,
    chat_id: int,
    photos_by_day: dict[str, list[StoredPhoto]],
    timezone: ZoneInfo,
) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for day_key in sorted(photos_by_day):
        for photo in photos_by_day[day_key]:
            writer.writerow(
                [
                    day_key,
                    photo.sender_label,
                    photo.dish,
                    photo.calories,
                    _format_local_time(photo.sent_at, timezone),
                    _telegram_message_link(chat_id, photo.message_id) or "",
                ]
            )
    return buffer.getvalue().encode("utf-8")


def csv_filename(*, start: str, end: str) -> str:
    if start == end:
        return f"{CSV_FILENAME_PREFIX}_{start}.csv"
    return f"{CSV_FILENAME_PREFIX}_{start}_to_{end}.csv"


def _telegram_message_link(chat_id: int, message_id: int) -> str | None:
    # Local uploads use synthetic negative message_ids; they have no Telegram link.
    if message_id <= 0:
        return None
    cid = str(chat_id)
    # Supergroups/channels have ids like -100xxxxxxxxxx; the public permalink
    # uses the digits after the -100 prefix. Legacy small groups have no link.
    if cid.startswith("-100"):
        return f"https://t.me/c/{cid[4:]}/{message_id}"
    return None


def _format_local_time(value: datetime | None, timezone: ZoneInfo) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone).strftime("%Y-%m-%d %H:%M")
