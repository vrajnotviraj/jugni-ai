import hmac

from fastapi import Header, HTTPException, Request

from controllers.dispatch_update import Dependencies
from core.settings import Settings
from image_analyser.factory import ImageEstimator
from storage.photo_repository import PhotoRepository
from summary_analyser.factory import DaySummarizer
from telegram.api import TelegramBotApi


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_telegram(request: Request) -> TelegramBotApi:
    return request.app.state.telegram


def get_repo(request: Request) -> PhotoRepository:
    return request.app.state.repo


def get_image_estimator(request: Request) -> ImageEstimator:
    return request.app.state.image_estimator


def get_day_summarizer(request: Request) -> DaySummarizer:
    return request.app.state.day_summarizer


def get_deps(request: Request) -> Dependencies:
    return request.app.state.deps


def resolve_target_chat_id(settings: Settings, chat_id: int | None) -> int:
    target = chat_id if chat_id is not None else settings.telegram_group_chat_id
    if target:
        return target
    raise HTTPException(
        status_code=400,
        detail=(
            "Missing or zero chat_id. Set TELEGRAM_GROUP_CHAT_ID to the group's "
            "numeric id (groups are negative, e.g. -1001234567890) or pass "
            "chat_id explicitly. Post any message in the group, then check "
            "the server logs for 'webhook chat_id=...' to discover the id."
        ),
    )


def verify_webhook_secret(
    settings: Settings,
    received_secret: str | None,
) -> None:
    if not settings.telegram_webhook_secret:
        return
    if received_secret and hmac.compare_digest(
        received_secret, settings.telegram_webhook_secret
    ):
        return
    raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret.")


def verify_admin_secret(
    settings: Settings,
    received_secret: str | None,
) -> None:
    if not settings.admin_api_secret:
        return
    if received_secret and hmac.compare_digest(
        received_secret, settings.admin_api_secret
    ):
        return
    raise HTTPException(status_code=401, detail="Invalid admin API secret.")


def webhook_secret_header(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> str | None:
    return x_telegram_bot_api_secret_token


def admin_secret_header(
    x_admin_api_secret: str | None = Header(default=None),
) -> str | None:
    return x_admin_api_secret
