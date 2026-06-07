import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramApiError(RuntimeError):
    pass


class TelegramBotApi:
    def __init__(self, bot_token: str, *, dry_run: bool = False) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._file_base_url = f"https://api.telegram.org/file/bot{bot_token}"
        self._dry_run = dry_run

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 30,
    ) -> list[dict[str, Any]]:
        params: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset

        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            response = await client.get(f"{self._base_url}/getUpdates", params=params)

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        if response.status_code >= 400 or not body.get("ok", False):
            description = body.get("description") or response.text
            raise TelegramApiError(
                f"Telegram getUpdates failed ({response.status_code}): {description}"
            )
        return body.get("result", [])

    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        file_path = await self._get_file_path(file_id)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self._file_base_url}/{file_path}")
            response.raise_for_status()
            return response.content, media_type_for_path(file_path)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        link_preview_options: dict[str, Any] | None = None,
    ) -> None:
        if self._dry_run:
            print(
                f"\n[DRY-RUN telegram] chat_id={chat_id} "
                f"reply_to={reply_to_message_id} parse_mode={parse_mode} "
                f"reply_markup={reply_markup}\n{text}\n"
            )
            logger.info(
                "dry-run send to chat=%s reply_to=%s", chat_id, reply_to_message_id
            )
            return

        if chat_id == 0:
            raise TelegramApiError(
                "Refusing to send to chat_id=0. Set TELEGRAM_GROUP_CHAT_ID to the "
                "group's numeric id (groups are negative, e.g. -1001234567890)."
            )

        payload: dict[str, object] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if link_preview_options is not None:
            payload["link_preview_options"] = link_preview_options
        if reply_to_message_id is not None and reply_to_message_id > 0:
            payload["reply_parameters"] = {
                "message_id": reply_to_message_id,
                "allow_sending_without_reply": True,
            }

        await self._call("sendMessage", payload)

    async def send_document(
        self,
        chat_id: int,
        filename: str,
        content: bytes,
        *,
        mime_type: str = "application/octet-stream",
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> None:
        if self._dry_run:
            print(
                f"\n[DRY-RUN telegram] sendDocument chat_id={chat_id} "
                f"file={filename} bytes={len(content)} caption={caption!r}\n"
            )
            logger.info(
                "dry-run send document to chat=%s file=%s bytes=%s",
                chat_id,
                filename,
                len(content),
            )
            return

        if chat_id == 0:
            raise TelegramApiError(
                "Refusing to send document to chat_id=0. Set TELEGRAM_GROUP_CHAT_ID."
            )

        data: dict[str, str] = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
        if parse_mode:
            data["parse_mode"] = parse_mode
        files = {"document": (filename, content, mime_type)}

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self._base_url}/sendDocument", data=data, files=files
            )

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        if response.status_code >= 400 or not body.get("ok", False):
            description = body.get("description") or response.text
            raise TelegramApiError(
                f"Telegram sendDocument failed ({response.status_code}): {description}"
            )

    async def set_my_commands(
        self,
        commands: list[dict[str, str]],
        scope: dict[str, str] | None = None,
    ) -> None:
        scope_label = scope["type"] if scope else "default"
        if self._dry_run:
            print(
                f"\n[DRY-RUN telegram] setMyCommands scope={scope_label} "
                f"count={len(commands)}\n"
                + "\n".join(f"  /{c['command']} - {c['description']}" for c in commands)
                + "\n"
            )
            logger.info(
                "dry-run setMyCommands scope=%s count=%s", scope_label, len(commands)
            )
            return

        payload: dict[str, object] = {"commands": commands}
        if scope is not None:
            payload["scope"] = scope
        await self._call("setMyCommands", payload)

    async def _call(self, method: str, payload: dict[str, object]) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self._base_url}/{method}", json=payload)

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        if response.status_code >= 400 or not body.get("ok", False):
            description = body.get("description") or response.text
            raise TelegramApiError(
                f"Telegram {method} failed ({response.status_code}): {description}"
            )
        return body

    async def _get_file_path(self, file_id: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self._base_url}/getFile",
                params={"file_id": file_id},
            )
            response.raise_for_status()

        payload = response.json()
        if not payload.get("ok"):
            raise TelegramApiError(f"Telegram getFile failed: {payload}")
        return payload["result"]["file_path"]


def media_type_for_path(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"
