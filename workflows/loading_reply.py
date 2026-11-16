"""The loading → result lifecycle shared by photo, /intake and /recommend.

A placeholder acknowledges the request at once: in private chats an animated
Bot API 10.4 HTML widget, in groups (where widgets aren't allowed) a looping
GIF. It is updated in place as the pipeline makes progress; the finished card
is then sent as a widget (private chats) or a Bot API 10.1 rich message,
falling back to the classic HTML text, and the placeholder is deleted. Every
step is best-effort except the reply itself: a lost placeholder or a failed
progress edit never blocks the card.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from domain.analysis import FoodAnalysis
from telegram.api import TelegramBotApi

logger = logging.getLogger(__name__)

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOADING_GIF = _ASSETS / "loading.gif"
LOADING_WIDGET = (_ASSETS / "widgets" / "loading.html").read_text()


def _is_private(chat_id: int) -> bool:
    # Telegram user chats have positive ids, groups negative; widgets are DM-only.
    return chat_id > 0


@dataclass(frozen=True, slots=True)
class Reply:
    # Classic parse_mode=HTML text; always deliverable, used as the fallback.
    text: str
    # Rich-message HTML (Bot API 10.1). None sends the classic text directly.
    rich_html: str | None = None
    link_preview_options: dict | None = None
    # (widget html, chat_data) for private chats; None skips the widget.
    widget: tuple[str, str] | None = None


async def start_loading(
    telegram: TelegramBotApi, chat_id: int, reply_to: int | None, caption: str
) -> int | None:
    if _is_private(chat_id):
        try:
            return await telegram.send_widget(
                chat_id, LOADING_WIDGET, json.dumps({"label": caption}), reply_to
            )
        except Exception:
            logger.exception("loading widget send failed chat=%s", chat_id)
    try:
        return await telegram.send_animation(chat_id, LOADING_GIF, caption, reply_to)
    except Exception:
        logger.exception("loading gif send failed chat=%s", chat_id)
    try:
        return await telegram.send_message(
            chat_id, caption, reply_to_message_id=reply_to
        )
    except Exception:
        logger.exception("loading text send failed chat=%s", chat_id)
        return None


def progress_caption(extraction: FoodAnalysis) -> str:
    return f"✅ {extraction.dish} · {extraction.calories} kcal\n✍️ Writing your tip…"


async def update_loading(
    telegram: TelegramBotApi,
    chat_id: int,
    placeholder_id: int | None,
    extraction: FoodAnalysis,
) -> None:
    if placeholder_id is None:
        return
    if _is_private(chat_id):
        data = {
            "label": "Writing your tip",
            "dish": extraction.dish,
            "kcal": extraction.calories,
        }
        try:
            await telegram.edit_message_widget_data(
                chat_id, placeholder_id, json.dumps(data, ensure_ascii=False)
            )
            return
        except Exception:
            # The placeholder fell back to the GIF; edit its caption instead.
            logger.info("loading widget update failed chat=%s", chat_id)
    try:
        await telegram.edit_message_caption(
            chat_id, placeholder_id, progress_caption(extraction)
        )
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
    if reply.widget is not None and _is_private(chat_id):
        try:
            await telegram.send_widget(chat_id, *reply.widget, reply_to)
            sent = True
        except Exception:
            logger.exception("widget reply failed chat=%s — sending rich", chat_id)
    if not sent and reply.rich_html is not None:
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
                reply_to_message_id=reply_to,
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
