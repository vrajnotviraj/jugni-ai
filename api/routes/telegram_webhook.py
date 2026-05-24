from fastapi import APIRouter, Depends, Request

from api.dependencies import (
    get_deps,
    get_settings,
    verify_webhook_secret,
    webhook_secret_header,
)
from controllers.dispatch_update import Dependencies, dispatch_update
from core.settings import Settings

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
    await dispatch_update(update, deps=deps)
    return {"ok": True}
