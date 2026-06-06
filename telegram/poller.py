import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)

UpdateHandler = Callable[[dict[str, Any]], Awaitable[None]]

# An explicit list REPLACES Telegram's default (which omits callback_query):
# "message" must stay in it or photo and command handling silently breaks.
# Webhook deployments must set the same allowed_updates on setWebhook.
ALLOWED_UPDATES = ["message", "callback_query"]


async def poll_telegram_forever(
    telegram: TelegramBotApi,
    *,
    on_update: UpdateHandler,
) -> None:
    offset: int | None = None
    backoff = 5

    while True:
        try:
            updates = await telegram.get_updates(
                offset=offset, timeout=30, allowed_updates=ALLOWED_UPDATES
            )
            for update in updates:
                offset = int(update["update_id"]) + 1
                try:
                    await on_update(update)
                except Exception:
                    logger.exception(
                        "polling: failed to handle update %s",
                        update.get("update_id"),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("polling: getUpdates failed, retrying in %ss", backoff)
            await asyncio.sleep(backoff)
