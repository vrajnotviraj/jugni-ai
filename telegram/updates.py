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
class DeleteCommand:
    chat_id: int
    target_message_id: int
    requester_sender_id: int | None


@dataclass(frozen=True, slots=True)
class Ignore:
    pass


ParsedUpdate = PhotoMessage | SummaryCommand | DeleteCommand | Ignore


def parse_update(update: dict[str, Any]) -> ParsedUpdate:
    message = _message_from_update(update)
    chat_type = message.get("chat", {}).get("type")
    if chat_type not in GROUP_CHAT_TYPES:
        return Ignore()

    if _is_summary_command(message):
        return SummaryCommand(chat_id=int(message["chat"]["id"]))

    delete_command = _parse_delete_command(message)
    if delete_command is not None:
        return delete_command

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
    return _leading_command(message) == "/summary"


def _parse_delete_command(message: dict[str, Any]) -> "DeleteCommand | None":
    if _leading_command(message) != "/delete":
        return None

    replied = message.get("reply_to_message") or {}
    if not replied.get("photo"):
        return None

    sender = message.get("from") or {}
    return DeleteCommand(
        chat_id=int(message["chat"]["id"]),
        target_message_id=int(replied["message_id"]),
        requester_sender_id=sender.get("id"),
    )


def _leading_command(message: dict[str, Any]) -> str | None:
    text = message.get("text", "")
    if not text.strip():
        return None
    return text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
