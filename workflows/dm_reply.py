import logging

from presenters.profile_reply import PROFILE_REPLY_PARSE_MODE
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)

_PREVIEW_LIMIT = 180


async def send_dm(telegram: TelegramBotApi, chat_id: int, text: str) -> None:
    """Send a DM reply, swallowing transport errors the way photo replies do.

    A failed send must not crash the dispatch loop; the write the user asked for
    has already happened by the time we reply. This is the single chokepoint for
    every DM reply, so it logs the outgoing response for debugging.
    """
    logger.info(
        "dm response chat=%s chars=%s preview=%r",
        chat_id,
        len(text),
        _preview(text),
    )
    try:
        await telegram.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=PROFILE_REPLY_PARSE_MODE,
        )
    except Exception:
        logger.exception("failed to send DM reply to chat=%s", chat_id)


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _PREVIEW_LIMIT:
        return flat
    return flat[:_PREVIEW_LIMIT] + "..."
