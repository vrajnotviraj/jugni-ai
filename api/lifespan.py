import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from openai import AsyncOpenAI

from analyzers.context.rewriter import build_context_rewriter
from analyzers.image.factory import build_image_estimator
from analyzers.profile.extractor import build_profile_extractor
from analyzers.recommend.factory import build_recommender
from analyzers.summary.factory import build_day_summarizer
from core.logging import configure_logging
from core.settings import Settings
from storage.factory import (
    build_photo_repository,
    build_profile_repository,
    build_webhook_dedupe,
)
from telegram.api import TelegramBotApi
from telegram.commands import bot_commands, group_commands
from telegram.poller import poll_telegram_forever
from workflows.dispatch_update import Dependencies, dispatch_update

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_environment()
    _warn_if_webhook_secret_missing(settings)
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    telegram = TelegramBotApi(
        settings.telegram_bot_token,
        dry_run=settings.telegram_dry_run,
    )
    repo = build_photo_repository(settings)
    profile_repo = build_profile_repository(settings)
    webhook_dedupe = build_webhook_dedupe(settings)
    image_estimator = build_image_estimator(settings, openai_client)
    day_summarizer = build_day_summarizer(settings, openai_client)
    profile_extractor = build_profile_extractor(settings, openai_client)
    context_rewriter = build_context_rewriter(settings, openai_client)
    recommender = build_recommender(settings, openai_client)

    deps = Dependencies(
        repo=repo,
        profile_repo=profile_repo,
        image_estimator=image_estimator,
        day_summarizer=day_summarizer,
        profile_extractor=profile_extractor,
        context_rewriter=context_rewriter,
        recommender=recommender,
        telegram=telegram,
        timezone=settings.timezone,
        allowed_chat_ids=settings.telegram_group_chat_ids,
    )

    app.state.settings = settings
    app.state.telegram = telegram
    app.state.repo = repo
    app.state.profile_repo = profile_repo
    app.state.webhook_dedupe = webhook_dedupe
    app.state.image_estimator = image_estimator
    app.state.day_summarizer = day_summarizer
    app.state.deps = deps

    await _register_bot_commands(telegram)

    polling_task: asyncio.Task[None] | None = None
    if settings.telegram_polling_enabled:
        polling_task = asyncio.create_task(
            poll_telegram_forever(
                telegram,
                on_update=lambda update: dispatch_update(update, deps=deps),
            )
        )
        logger.info(
            "telegram polling enabled (group_chat_ids=%s, dry_run=%s)",
            list(settings.telegram_group_chat_ids) or "*",
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
        await profile_repo.close()
        await webhook_dedupe.close()


async def _register_bot_commands(telegram: TelegramBotApi) -> None:
    # Idempotent: registers the DM and group command menus on every boot, each
    # scoped so the client only offers profile/help commands in private chats and
    # only /summary and /delete in groups. A failure here must not stop the app
    # from serving, so we log and move on.
    try:
        await telegram.set_my_commands(
            bot_commands(), scope={"type": "all_private_chats"}
        )
        await telegram.set_my_commands(
            group_commands(), scope={"type": "all_group_chats"}
        )
        logger.info(
            "registered %s private and %s group bot commands",
            len(bot_commands()),
            len(group_commands()),
        )
    except Exception:
        logger.exception("failed to register bot commands at startup")


def _warn_if_webhook_secret_missing(settings: Settings) -> None:
    # The bot now accepts private messages and writes health data keyed by the
    # sender's user id. Without the webhook secret, verify_webhook_secret returns
    # early and a forged update could write under any user id. We warn loudly
    # rather than hard-fail so local and admin-only runs still boot.
    if not settings.telegram_webhook_secret:
        logger.warning(
            "TELEGRAM_WEBHOOK_SECRET is not set. The Telegram webhook is "
            "UNAUTHENTICATED and forged updates could write profile data under "
            "arbitrary user ids. Set it before exposing /api/telegram/webhook."
        )
