"""The loading → result lifecycle shared by photo, /intake and /recommend.

A looping GIF acknowledges the request at once; its caption is updated as the
pipeline makes progress; the finished card is then sent as a Bot API 10.1 rich
message (falling back to the classic HTML text) and the GIF is deleted. Every
step is best-effort except the reply itself: a lost GIF or a failed caption
edit never blocks the card.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)

LOADING_GIF = Path(__file__).resolve().parent.parent / "assets" / "loading.gif"


@dataclass(frozen=True, slots=True)
class Reply:
    # Classic parse_mode=HTML text; always deliverable, used as the fallback.
    text: str
    # Rich-message HTML (Bot API 10.1). None sends the classic text directly.
    rich_html: str | None = None
    link_preview_options: dict | None = None


async def start_loading(
    telegram: TelegramBotApi, chat_id: int, reply_to: int | None, caption: str
) -> int | None:
    try:
        return await telegram.send_animation(chat_id, LOADING_GIF, caption, reply_to)
    except Exception:
        logger.exception("loading gif send failed chat=%s", chat_id)
    try:
        return await telegram.send_message(chat_id, caption, reply_to)
    except Exception:
        logger.exception("loading text send failed chat=%s", chat_id)
        return None


async def update_loading(
    telegram: TelegramBotApi, chat_id: int, placeholder_id: int | None, caption: str
) -> None:
    if placeholder_id is None:
        return
    try:
        await telegram.edit_message_caption(chat_id, placeholder_id, caption)
    except Exception:
        # Also lands here when the placeholder fell back to a text message.
        logger.warning("loading caption update failed chat=%s", chat_id)


async def finish_loading(
    telegram: TelegramBotApi,
    chat_id: int,
    reply_to: int | None,
    placeholder_id: int | None,
    reply: Reply,
) -> None:
    """Send the result, then remove the loading message. The placeholder is only
    deleted once a reply landed, so the chat is never left silent."""
    sent = False
    if reply.rich_html is not None:
        try:
            await telegram.send_rich_message(chat_id, reply.rich_html, reply_to)
            sent = True
        except Exception:
            logger.exception("rich reply failed chat=%s — sending classic", chat_id)
    if not sent:
        try:
            await telegram.send_message(
                chat_id,
                reply.text,
                reply_to,
                parse_mode="HTML",
                link_preview_options=reply.link_preview_options,
            )
            sent = True
        except Exception:
            logger.exception("reply failed chat=%s", chat_id)
    if sent and placeholder_id is not None:
        try:
            await telegram.delete_message(chat_id, placeholder_id)
        except Exception:
            logger.warning("loading message delete failed chat=%s", chat_id)
