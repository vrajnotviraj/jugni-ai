"""Admin-only endpoints for exercising the private (DM) profile surface over HTTP.

These let you test the whole DM flow without a Telegram client. /simulate runs
the real dispatch path (parse, rate cap, workflow, presenter) against a capturing
Telegram so the response carries the exact reply text the user would receive.
All routes require X-Admin-API-Secret when ADMIN_API_SECRET is set.
"""

import logging
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import (
    admin_secret_header,
    get_deps,
    get_profile_repo,
    get_settings,
    get_telegram,
    verify_admin_secret,
)
from core.settings import Settings
from storage.profile_repository import ProfileRepository
from telegram.api import TelegramBotApi
from telegram.commands import bot_commands, group_commands
from workflows.dispatch_update import Dependencies, dispatch_update

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class SimulateCommandRequest(BaseModel):
    user_id: int = Field(description="Telegram user id to act as.")
    text: str = Field(description="The full command text, e.g. '/profile 72 kg'.")
    first_name: str = Field(
        default="Tester",
        description="Display name to attach to the simulated sender.",
    )


@router.post("/simulate")
async def simulate_command(
    payload: SimulateCommandRequest,
    settings: Settings = Depends(get_settings),
    deps: Dependencies = Depends(get_deps),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)

    logger.info(
        "admin simulate received user=%s text=%r", payload.user_id, payload.text
    )
    capture = _CapturingTelegram()
    test_deps = replace(deps, telegram=capture)
    update = _private_update(payload.user_id, payload.first_name, payload.text)

    await dispatch_update(update, deps=test_deps)

    return {
        "ok": True,
        "user_id": payload.user_id,
        "sent": bool(capture.replies),
        "replies": capture.replies,
    }


@router.get("/{user_id}")
async def get_profile(
    user_id: int,
    settings: Settings = Depends(get_settings),
    repo: ProfileRepository = Depends(get_profile_repo),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)

    profile = await repo.get_profile(user_id)
    context = await repo.list_context(user_id)
    weights = await repo.weight_history(user_id)

    return {
        "ok": True,
        "user_id": user_id,
        "profile": _profile_payload(profile),
        "context": context,
        "weight_history": [
            {"recorded_at": recorded_at.isoformat(), "weight_kg": weight}
            for recorded_at, weight in weights
        ],
    }


@router.delete("/{user_id}")
async def delete_profile(
    user_id: int,
    settings: Settings = Depends(get_settings),
    repo: ProfileRepository = Depends(get_profile_repo),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    await repo.delete_profile(user_id)
    return {"ok": True, "user_id": user_id, "deleted": True}


@router.post("/register-commands")
async def register_commands(
    settings: Settings = Depends(get_settings),
    telegram: TelegramBotApi = Depends(get_telegram),
    admin_secret: str | None = Depends(admin_secret_header),
) -> dict[str, Any]:
    verify_admin_secret(settings, admin_secret)
    private = bot_commands()
    group = group_commands()
    try:
        await telegram.set_my_commands(private, scope={"type": "all_private_chats"})
        await telegram.set_my_commands(group, scope={"type": "all_group_chats"})
    except Exception as error:
        logger.exception("admin register-commands failed")
        raise HTTPException(
            status_code=502, detail=f"setMyCommands failed: {error}"
        ) from error
    return {
        "ok": True,
        "private_count": len(private),
        "private_commands": private,
        "group_count": len(group),
        "group_commands": group,
    }


class _CapturingTelegram:
    """Stand-in Telegram that records replies instead of sending them.

    Only send_message is exercised by the private command workflows; that is all
    we need to capture for /simulate. Extra Telegram kwargs (reply_to, parse_mode)
    are accepted and ignored so the call signature stays compatible.
    """

    def __init__(self) -> None:
        self.replies: list[str] = []

    async def send_message(self, chat_id: int, text: str, **_kwargs: object) -> None:
        logger.debug("captured simulated reply to chat=%s", chat_id)
        self.replies.append(text)


def _private_update(user_id: int, first_name: str, text: str) -> dict[str, Any]:
    return {
        "update_id": 0,
        "message": {
            "message_id": 0,
            "date": 0,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "first_name": first_name},
            "text": text,
        },
    }


def _profile_payload(profile: Any) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "weight_updated_at": (
            profile.weight_updated_at.isoformat()
            if profile.weight_updated_at
            else None
        ),
        "age": profile.age,
        "sex": profile.sex,
        "activity": profile.activity,
        "goal": profile.goal,
        "diet": profile.diet,
        "timezone": profile.timezone,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
