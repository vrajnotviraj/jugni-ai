import logging

from fastapi import APIRouter, Depends, Request

from api.dependencies import (
    get_deps,
    get_settings,
    verify_webhook_secret,
    webhook_secret_header,
)
from core.settings import Settings
from workflows.dispatch_update import Dependencies, dispatch_update

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/telegram/webhook")
async def telegram_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    deps: Dependencies = Depends(get_deps),
    secret: str | None = Depends(webhook_secret_header),
) -> dict[str, bool]:
    verify_webhook_secret(settings, secret)
    update = await request.json()
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    logger.info(
        "webhook received update_id=%s chat_type=%s chat_id=%s has_photo=%s text=%r",
        update.get("update_id"),
        chat.get("type"),
        chat.get("id"),
        bool(message.get("photo")),
        (message.get("text") or "")[:80],
    )
    await dispatch_update(update, deps=deps)
    return {"ok": True}
