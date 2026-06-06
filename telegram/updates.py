from dataclasses import dataclass
from typing import Any

from domain.photo import Photo, sender_label_from

GROUP_CHAT_TYPES = {"group", "supergroup"}
PRIVATE_CHAT_TYPE = "private"


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


# --- Private (DM) commands. user_id is the person's global Telegram id; chat_id
# is where the reply goes (equal to user_id in a 1:1 chat). display_name is
# captured here so replies can address the user by name. ---


@dataclass(frozen=True, slots=True)
class ProfileCommand:
    user_id: int
    chat_id: int
    display_name: str
    text: str


# /context <free text>: one message the AI interprets as an add, change, or
# removal. Bare /context (no text) parses to ViewContextCommand instead.
@dataclass(frozen=True, slots=True)
class EditContextCommand:
    user_id: int
    chat_id: int
    display_name: str
    text: str


@dataclass(frozen=True, slots=True)
class ViewContextCommand:
    user_id: int
    chat_id: int


@dataclass(frozen=True, slots=True)
class DeleteProfileCommand:
    user_id: int
    chat_id: int


@dataclass(frozen=True, slots=True)
class HelpCommand:
    user_id: int
    chat_id: int
    display_name: str


# /recommend works on both surfaces; ``surface`` records which one so dispatch
# can keep the group allowlist gate. ``text`` is the raw argument string; the
# recommend workflow extracts the slot/modifier keywords itself. ``message_id``
# lets the group reply thread back to the command (and scope the slot keyboard
# to its sender via Telegram's ``selective`` flag).
@dataclass(frozen=True, slots=True)
class RecommendCommand:
    user_id: int
    chat_id: int
    message_id: int
    sender_label: str
    display_name: str
    text: str
    surface: str  # "dm" | "group"


@dataclass(frozen=True, slots=True)
class Ignore:
    pass


ParsedUpdate = (
    PhotoMessage
    | SummaryCommand
    | DeleteCommand
    | ProfileCommand
    | EditContextCommand
    | ViewContextCommand
    | DeleteProfileCommand
    | HelpCommand
    | RecommendCommand
    | Ignore
)


def parse_update(update: dict[str, Any]) -> ParsedUpdate:
    message = _message_from_update(update)
    chat_type = message.get("chat", {}).get("type")
    if chat_type in GROUP_CHAT_TYPES:
        return _parse_group_message(message, update)
    if chat_type == PRIVATE_CHAT_TYPE:
        return _parse_private_message(message)
    return Ignore()


def message_date(update: dict[str, Any]) -> int:
    return int(_message_from_update(update).get("date") or 0)


def chat_type_is_group(update: dict[str, Any]) -> bool:
    return _message_from_update(update).get("chat", {}).get("type") in GROUP_CHAT_TYPES


def _parse_group_message(
    message: dict[str, Any],
    update: dict[str, Any],
) -> ParsedUpdate:
    if _leading_command(message) == "/summary":
        return SummaryCommand(chat_id=int(message["chat"]["id"]))

    if _leading_command(message) == "/recommend":
        return _parse_recommend_command(message, surface="group")

    delete_command = _parse_delete_command(message)
    if delete_command is not None:
        return delete_command

    photo = Photo.from_telegram_update(update)
    if photo is not None:
        return PhotoMessage(photo=photo)

    return Ignore()


def _parse_private_message(message: dict[str, Any]) -> ParsedUpdate:
    command, args = _command_and_args(message)
    if command is None:
        return Ignore()

    sender = message.get("from") or {}
    user_id = sender.get("id")
    if user_id is None:
        return Ignore()
    user_id = int(user_id)
    chat_id = int(message["chat"]["id"])
    display_name = _display_name(sender)

    match command:
        case "/profile":
            return ProfileCommand(
                user_id=user_id,
                chat_id=chat_id,
                display_name=display_name,
                text=args,
            )
        case "/context":
            # Bare /context views the notes; any text is an AI-interpreted edit.
            if args:
                return EditContextCommand(
                    user_id=user_id,
                    chat_id=chat_id,
                    display_name=display_name,
                    text=args,
                )
            return ViewContextCommand(user_id=user_id, chat_id=chat_id)
        case "/recommend":
            return _parse_recommend_command(message, surface="dm")
        case "/deleteprofile":
            return DeleteProfileCommand(user_id=user_id, chat_id=chat_id)
        case "/start" | "/help":
            return HelpCommand(
                user_id=user_id, chat_id=chat_id, display_name=display_name
            )
        case _:
            return Ignore()


def _parse_recommend_command(
    message: dict[str, Any],
    *,
    surface: str,
) -> ParsedUpdate:
    sender = message.get("from") or {}
    user_id = sender.get("id")
    if user_id is None:
        return Ignore()
    _, args = _command_and_args(message)
    return RecommendCommand(
        user_id=int(user_id),
        chat_id=int(message["chat"]["id"]),
        message_id=int(message.get("message_id") or 0),
        sender_label=sender_label_from(sender),
        display_name=_display_name(sender),
        text=args,
        surface=surface,
    )


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


def _message_from_update(update: dict[str, Any]) -> dict[str, Any]:
    return update.get("message") or {}


def _leading_command(message: dict[str, Any]) -> str | None:
    command, _ = _command_and_args(message)
    return command


def _command_and_args(message: dict[str, Any]) -> tuple[str | None, str]:
    text = message.get("text", "")
    if not text.strip():
        return None, ""
    parts = text.split(maxsplit=1)
    command = parts[0].split("@", maxsplit=1)[0]
    args = parts[1].strip() if len(parts) > 1 else ""
    return command, args


def _display_name(sender: dict[str, Any]) -> str:
    first_name = (sender.get("first_name") or "").strip()
    if first_name:
        return first_name
    username = (sender.get("username") or "").strip()
    if username:
        return f"@{username}"
    return ""
