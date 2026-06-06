import logging

from fastapi import APIRouter, Depends, Request

from api.dependencies import (
    get_deps,
    get_settings,
    get_webhook_dedupe,
    verify_webhook_secret,
    webhook_secret_header,
)
from core.settings import Settings
from storage.webhook_dedupe import WebhookDedupe
from workflows.dispatch_update import Dependencies, dispatch_update

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/telegram/webhook")
async def telegram_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    deps: Dependencies = Depends(get_deps),
    dedupe: WebhookDedupe = Depends(get_webhook_dedupe),
    secret: str | None = Depends(webhook_secret_header),
) -> dict[str, bool]:
    verify_webhook_secret(settings, secret)
    update = await request.json()
    update_id = _safe_update_id(update.get("update_id"))
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    logger.info(
        "webhook received update_id=%s chat_type=%s chat_id=%s has_photo=%s text=%r",
        update_id,
        chat.get("type"),
        chat.get("id"),
        bool(message.get("photo")),
        (message.get("text") or "")[:80],
    )
    if await dedupe.was_sent(update_id):
        logger.info("webhook duplicate acked update_id=%s", update_id)
        return {"ok": True}
    await dispatch_update(update, deps=deps)
    await dedupe.mark_sent(update_id)
    return {"ok": True}


def _safe_update_id(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
