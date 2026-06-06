"""Admin-only endpoint for simulating Telegram traffic on either surface.

POST /api/telegram/simulate runs a synthetic DM or group message — or an
inline-button press — through the real dispatch path (parse, allowlist, rate
cap, workflow, presenter) against a capturing Telegram, so the response
carries exactly what the bot would have sent. This is how to exercise
/recommend (including its keyboard) without a Telegram client; the existing
/api/profiles/simulate stays as the DM-profile shortcut.

Requires X-Admin-API-Secret when ADMIN_API_SECRET is set.
"""

import logging
from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import (
    admin_secret_header,
    get_deps,
    get_settings,
    resolve_target_chat_id,
    verify_admin_secret,
)
from core.settings import Settings
from workflows.dispatch_update import Dependencies, dispatch_update

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telegram", tags=["simulate"])


class SimulateRequest(BaseModel):
    user_id: int = Field(description="Telegram user id to act as.")
    surface: Literal["dm", "group"] = Field(
        default="dm", description="Where the update happens."
    )
    text: str = Field(
        default="", description="Message text, e.g. '/recommend dinner'."
    )
    callback_data: str | None = Field(
        default=None,
        description=(
            "Simulate an inline-button press with this callback_data (e.g. "
            "'rec:<user_id>:dinner') instead of a text message."
        ),
    )
    chat_id: int | None = Field(
        default=None,
        description="Group chat id; defaults to the configured group.",
    )
    username: str | None = Field(
        default=None,
        description=(
            "Sender username (without @). Meals are stored under '@username', "
            "so set it to match when history should be found."
        ),
    )
    first_name: str = Field(default="Tester")


@router.post("/simulate")
async def simulate_update(
    payload: SimulateRequest,
    settings: Settings = Depends(get_settings),
    deps: Dependencies = Depends(get_deps),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)

    if payload.surface == "group":
        chat = {
            "id": resolve_target_chat_id(settings, payload.chat_id),
            "type": "supergroup",
        }
    else:
        chat = {"id": payload.user_id, "type": "private"}
    sender: dict[str, Any] = {"id": payload.user_id, "first_name": payload.first_name}
    if payload.username:
        sender["username"] = payload.username

    if payload.callback_data is not None:
        update: dict[str, Any] = {
            "update_id": 0,
            "callback_query": {
                "id": "simulated",
                "from": sender,
                "message": {"message_id": 0, "chat": chat},
                "data": payload.callback_data,
            },
        }
    else:
        update = {
            "update_id": 0,
            "message": {
                "message_id": 0,
                "date": 0,
                "chat": chat,
                "from": sender,
                "text": payload.text,
            },
        }

    logger.info(
        "admin simulate user=%s surface=%s text=%r callback=%r",
        payload.user_id,
        payload.surface,
        payload.text,
        payload.callback_data,
    )
    capture = _CapturingTelegram()
    await dispatch_update(update, deps=replace(deps, telegram=capture))

    return {
        "ok": True,
        "user_id": payload.user_id,
        "surface": payload.surface,
        "replies": capture.replies,
        "callback_answers": capture.callback_answers,
    }


class _CapturingTelegram:
    """Records what the bot would send, including keyboards and press acks,
    so a /recommend keyboard's callback_data can be read and pressed next."""

    def __init__(self) -> None:
        self.replies: list[dict[str, Any]] = []
        self.callback_answers: list[dict[str, Any]] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        **_kwargs: object,
    ) -> None:
        self.replies.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        self.callback_answers.append({"text": text, "show_alert": show_alert})
