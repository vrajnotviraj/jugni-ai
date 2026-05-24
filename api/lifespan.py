import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from openai import AsyncOpenAI

from controllers.dispatch_update import Dependencies, dispatch_update
from core.logging import configure_logging
from core.settings import Settings
from image_analyser.factory import build_image_estimator
from storage.factory import build_photo_repository
from summary_analyser.factory import build_day_summarizer
from telegram.api import TelegramBotApi
from telegram.poller import poll_telegram_forever

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_environment()
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    telegram = TelegramBotApi(
        settings.telegram_bot_token,
        dry_run=settings.telegram_dry_run,
    )
    repo = build_photo_repository(settings)
    image_estimator = build_image_estimator(settings, openai_client)
    day_summarizer = build_day_summarizer(settings, openai_client)

    deps = Dependencies(
        repo=repo,
        image_estimator=image_estimator,
        day_summarizer=day_summarizer,
        telegram=telegram,
        timezone=settings.timezone,
        configured_group_chat_id=settings.telegram_group_chat_id,
    )

    app.state.settings = settings
    app.state.telegram = telegram
    app.state.repo = repo
    app.state.image_estimator = image_estimator
    app.state.day_summarizer = day_summarizer
    app.state.deps = deps

    polling_task: asyncio.Task[None] | None = None
    if settings.telegram_polling_enabled:
        polling_task = asyncio.create_task(
            poll_telegram_forever(
                telegram,
                on_update=lambda update: dispatch_update(update, deps=deps),
            )
        )
        logger.info(
            "telegram polling enabled (group_chat_id=%s, dry_run=%s)",
            settings.telegram_group_chat_id,
            settings.telegram_dry_run,
        )
    else:
        logger.info(
            "telegram polling disabled; webhook mode (dry_run=%s)",
            settings.telegram_dry_run,
        )

    try:
        yield
    finally:
        if polling_task is not None:
            polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await polling_task
        await repo.close()
