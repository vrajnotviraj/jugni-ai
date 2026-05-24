from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import (
    admin_secret_header,
    get_deps,
    get_settings,
    get_telegram,
    verify_admin_secret,
)
from controllers.dispatch_update import Dependencies, dispatch_update
from core.settings import Settings
from telegram.api import TelegramBotApi
from telegram.backfill import backfill_cutoff_epoch, cutoff_iso, run_backfill

router = APIRouter()


@router.post("/api/backfill")
async def backfill_telegram_updates(
    since: str | None = Query(
        default=None,
        description=(
            "ISO date (YYYY-MM-DD) for the cutoff start-of-day in APP_TIMEZONE. "
            "Defaults to yesterday."
        ),
    ),
    settings: Settings = Depends(get_settings),
    telegram: TelegramBotApi = Depends(get_telegram),
    deps: Dependencies = Depends(get_deps),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    _require_polling_disabled(settings)

    try:
        epoch = backfill_cutoff_epoch(since, settings.timezone)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    counts = await run_backfill(
        telegram,
        cutoff_epoch=epoch,
        on_update=lambda update: dispatch_update(update, deps=deps),
    )

    return {
        "ok": True,
        "cutoff_epoch": counts.cutoff_epoch,
        "cutoff_iso": cutoff_iso(counts.cutoff_epoch, settings.timezone),
        "received": counts.received,
        "processed": counts.processed,
        "skipped_old": counts.skipped_old,
        "skipped_non_group": counts.skipped_non_group,
        "errors": counts.errors,
        "last_update_id": counts.last_update_id,
    }


def _require_polling_disabled(settings: Settings) -> None:
    if not settings.telegram_polling_enabled:
        return
    raise HTTPException(
        status_code=409,
        detail=(
            "Telegram polling is enabled. Disable it (TELEGRAM_POLLING_ENABLED=0) "
            "and restart before running backfill — otherwise the poller will race "
            "for the same updates."
        ),
    )
