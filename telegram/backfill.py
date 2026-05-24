import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

from telegram.api import TelegramBotApi
from telegram.updates import chat_type_is_group, message_date

logger = logging.getLogger(__name__)

UpdateHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class BackfillCounts:
    processed: int
    skipped_old: int
    skipped_non_group: int
    errors: int
    last_update_id: int | None
    received: int
    cutoff_epoch: int


def backfill_cutoff_epoch(since: str | None, timezone: ZoneInfo) -> int:
    if since:
        try:
            cutoff_date = datetime.strptime(since.strip(), "%Y-%m-%d").date()
        except ValueError as error:
            raise ValueError(
                "Invalid since. Use YYYY-MM-DD "
                "(interpreted as start-of-day in APP_TIMEZONE)."
            ) from error
    else:
        cutoff_date = datetime.now(tz=timezone).date() - timedelta(days=1)

    cutoff_local = datetime.combine(cutoff_date, dtime.min, tzinfo=timezone)
    return int(cutoff_local.timestamp())


def cutoff_iso(cutoff_epoch: int, timezone: ZoneInfo) -> str:
    return (
        datetime.fromtimestamp(cutoff_epoch, tz=UTC)
        .astimezone(timezone)
        .isoformat()
    )


async def run_backfill(
    telegram: TelegramBotApi,
    *,
    cutoff_epoch: int,
    on_update: UpdateHandler,
) -> BackfillCounts:
    updates = await telegram.get_updates(offset=None, timeout=0)
    processed = 0
    skipped_old = 0
    skipped_non_group = 0
    errors = 0
    last_update_id: int | None = None

    for update in updates:
        last_update_id = _max_update_id(last_update_id, update)
        outcome = await _dispatch(update, cutoff_epoch, on_update)
        if outcome == "processed":
            processed += 1
        elif outcome == "too_old":
            skipped_old += 1
        elif outcome == "non_group":
            skipped_non_group += 1
        else:
            errors += 1

    await _ack_updates(telegram, last_update_id)

    return BackfillCounts(
        processed=processed,
        skipped_old=skipped_old,
        skipped_non_group=skipped_non_group,
        errors=errors,
        last_update_id=last_update_id,
        received=len(updates),
        cutoff_epoch=cutoff_epoch,
    )


async def _dispatch(
    update: dict[str, Any],
    cutoff_epoch: int,
    on_update: UpdateHandler,
) -> str:
    msg_date = message_date(update)
    if msg_date and msg_date < cutoff_epoch:
        return "too_old"
    if not chat_type_is_group(update):
        return "non_group"

    try:
        await on_update(update)
    except Exception:
        logger.exception(
            "backfill: failed to handle update %s",
            update.get("update_id"),
        )
        return "error"
    return "processed"


def _max_update_id(current: int | None, update: dict[str, Any]) -> int | None:
    update_id = int(update.get("update_id", 0))
    if not update_id:
        return current
    if current is None:
        return update_id
    return max(current, update_id)


async def _ack_updates(telegram: TelegramBotApi, last_update_id: int | None) -> None:
    if last_update_id is None:
        return
    try:
        await telegram.get_updates(offset=last_update_id + 1, timeout=0)
    except Exception:
        logger.exception("backfill: failed to ack updates up to %s", last_update_id)
