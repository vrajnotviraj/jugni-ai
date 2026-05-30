import logging
from collections.abc import Callable, Coroutine
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

from analyzers.profile.prompts import (
    PROFILE_EXTRACTION_SYSTEM_PROMPT,
    profile_extraction_user_prompt,
)
from core.settings import Settings
from domain.profile import ProfileExtraction
from llm.json_parsing import parse_fenced_json
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)

ProfileExtractor = Callable[[str], Coroutine[Any, Any, ProfileExtraction]]


def build_profile_extractor(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> ProfileExtractor:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    model = settings.openai_model

    async def extractor(text: str) -> ProfileExtraction:
        return await extract_profile(openai_client, model=model, text=text)

    return extractor

# Plausibility guards: anything outside these is treated as a misread and dropped.
_HEIGHT_MIN_CM, _HEIGHT_MAX_CM = 100, 250
_WEIGHT_MIN_KG, _WEIGHT_MAX_KG = 20.0, 300.0
_AGE_MIN, _AGE_MAX = 13, 100
_GOAL_MAX_LEN = 80
_DIET_MAX_LEN = 120
_VALID_SEX = {"male", "female"}
_VALID_ACTIVITY = {"sedentary", "light", "moderate", "active", "very_active"}


async def extract_profile(
    client: AsyncOpenAI,
    *,
    model: str,
    text: str,
) -> ProfileExtraction:
    """Turn a natural-language message into validated profile fields.

    Never raises: malformed model output yields an empty extraction so the
    workflow can show "I didn't catch that" guidance instead of an error.
    """
    try:
        raw = await call_responses(
            client,
            model=model,
            system=PROFILE_EXTRACTION_SYSTEM_PROMPT,
            user=profile_extraction_user_prompt(text),
            cache_key="profile-extraction",
        )
        payload = parse_fenced_json(raw)
    except Exception:
        logger.exception("profile extraction failed")
        return ProfileExtraction()

    extraction = _validate(payload)
    logger.info(
        "profile extraction parsed fields=%s ignored=%s",
        sorted(extraction.to_fields().keys()),
        list(extraction.ignored),
    )
    return extraction


def _validate(payload: dict[str, object]) -> ProfileExtraction:
    ignored: list[str] = []

    height_cm = _ranged_int(
        payload.get("height_cm"), _HEIGHT_MIN_CM, _HEIGHT_MAX_CM, "height", ignored
    )
    weight_kg = _ranged_float(
        payload.get("weight_kg"), _WEIGHT_MIN_KG, _WEIGHT_MAX_KG, "weight", ignored
    )
    age = _ranged_int(payload.get("age"), _AGE_MIN, _AGE_MAX, "age", ignored)
    sex = _one_of(payload.get("sex"), _VALID_SEX)
    activity = _one_of(payload.get("activity"), _VALID_ACTIVITY)
    timezone = _valid_zone(payload.get("timezone"), ignored)
    goal = _short_text(payload.get("goal"), _GOAL_MAX_LEN)
    diet = _short_text(payload.get("diet"), _DIET_MAX_LEN)

    return ProfileExtraction(
        height_cm=height_cm,
        weight_kg=weight_kg,
        age=age,
        sex=sex,
        activity=activity,
        goal=goal,
        diet=diet,
        timezone=timezone,
        ignored=tuple(ignored),
    )


def _ranged_int(
    value: object,
    low: int,
    high: int,
    label: str,
    ignored: list[str],
) -> int | None:
    if value is None:
        return None
    try:
        number = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if low <= number <= high:
        return number
    ignored.append(label)
    return None


def _ranged_float(
    value: object,
    low: float,
    high: float,
    label: str,
    ignored: list[str],
) -> float | None:
    if value is None:
        return None
    try:
        number = round(float(value), 1)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if low <= number <= high:
        return number
    ignored.append(label)
    return None


def _valid_zone(value: object, ignored: list[str]) -> str | None:
    if value is None:
        return None
    name = str(value).strip()
    if not name:
        return None
    try:
        ZoneInfo(name)
    except Exception:
        ignored.append("timezone")
        return None
    return name


def _one_of(value: object, allowed: set[str]) -> str | None:
    if value is None:
        return None
    normalised = str(value).strip().lower()
    return normalised if normalised in allowed else None


def _short_text(value: object, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len].strip()
