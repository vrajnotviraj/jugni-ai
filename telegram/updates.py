from dataclasses import dataclass
from typing import Any

from domain.photo import Photo

GROUP_CHAT_TYPES = {"group", "supergroup"}


@dataclass(frozen=True, slots=True)
class PhotoMessage:
    photo: Photo


@dataclass(frozen=True, slots=True)
class SummaryCommand:
    chat_id: int


@dataclass(frozen=True, slots=True)
class Ignore:
    pass


ParsedUpdate = PhotoMessage | SummaryCommand | Ignore


def parse_update(update: dict[str, Any]) -> ParsedUpdate:
    message = _message_from_update(update)
    chat_type = message.get("chat", {}).get("type")
    if chat_type not in GROUP_CHAT_TYPES:
        return Ignore()

    if _is_summary_command(message):
        return SummaryCommand(chat_id=int(message["chat"]["id"]))

    photo = Photo.from_telegram_update(update)
    if photo is not None:
        return PhotoMessage(photo=photo)

    return Ignore()


def message_date(update: dict[str, Any]) -> int:
    return int(_message_from_update(update).get("date") or 0)


def chat_type_is_group(update: dict[str, Any]) -> bool:
    return _message_from_update(update).get("chat", {}).get("type") in GROUP_CHAT_TYPES


def _message_from_update(update: dict[str, Any]) -> dict[str, Any]:
    return update.get("message") or update.get("edited_message") or {}


def _is_summary_command(message: dict[str, Any]) -> bool:
    text = message.get("text", "")
    if not text.strip():
        return False
    command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
    return command == "/summary"
