import hmac

from fastapi import Header, HTTPException, Request

from analyzers.image.factory import ImageEstimator
from analyzers.summary.factory import DaySummarizer
from core.settings import Settings
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from workflows.dispatch_update import Dependencies


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_telegram(request: Request) -> TelegramBotApi:
    return request.app.state.telegram


def get_repo(request: Request) -> PhotoRepository:
    return request.app.state.repo


def get_profile_repo(request: Request) -> ProfileRepository:
    return request.app.state.profile_repo


def get_image_estimator(request: Request) -> ImageEstimator:
    return request.app.state.image_estimator


def get_day_summarizer(request: Request) -> DaySummarizer:
    return request.app.state.day_summarizer


def get_deps(request: Request) -> Dependencies:
    return request.app.state.deps


def resolve_target_chat_id(settings: Settings, chat_id: int | None) -> int:
    if chat_id:
        return chat_id
    configured = settings.telegram_group_chat_ids
    if len(configured) == 1:
        return configured[0]
    raise HTTPException(
        status_code=400,
        detail=(
            "Pass chat_id explicitly when TELEGRAM_GROUP_CHAT_ID has "
            f"{len(configured)} groups configured."
        ),
    )


def verify_cron_secret(settings: Settings, authorization: str | None) -> None:
    if not settings.cron_secret:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET is not configured on the server.",
        )
    expected = f"Bearer {settings.cron_secret}"
    if authorization and hmac.compare_digest(authorization, expected):
        return
    raise HTTPException(status_code=401, detail="Invalid cron secret.")


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
