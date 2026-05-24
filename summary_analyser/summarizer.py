import logging

from openai import AsyncOpenAI

from ai.openai_client import call_responses
from domain.day import DayNote, Meal
from summary_analyser.parser import parse_day_note, parse_rerank_scores
from summary_analyser.prompts import (
    DAY_RERANK_SYSTEM_PROMPT,
    DAY_SUMMARY_SYSTEM_PROMPT,
    GENERAL_DAY_NOTE_FALLBACK,
)

logger = logging.getLogger(__name__)


async def write_day_note(
    client: AsyncOpenAI,
    *,
    model: str,
    meals: list[Meal],
) -> DayNote:
    if not meals:
        return DayNote(summary="", health_score=0)

    total = sum(meal.calories for meal in meals)
    formatted_meals = ", ".join(_format_meal(meal) for meal in meals if meal.dish)
    if not formatted_meals:
        return DayNote(summary=GENERAL_DAY_NOTE_FALLBACK, health_score=5)

    user_prompt = (
        f"Meals today (chronological): [{formatted_meals}]. Total: {total} kcal. "
        "Return the JSON described in the system prompt."
    )

    try:
        raw = await call_responses(
            client,
            model=model,
            system=DAY_SUMMARY_SYSTEM_PROMPT,
            user=user_prompt,
        )
        return parse_day_note(raw)
    except Exception:
        logger.exception("day summary note generation failed")
        return DayNote(summary=GENERAL_DAY_NOTE_FALLBACK, health_score=5)


async def rerank_day_scores(
    client: AsyncOpenAI,
    *,
    model: str,
    users: list[tuple[str, list[Meal], DayNote]],
) -> dict[str, int]:
    fallback = {label: note.health_score for label, _, note in users}

    if len(users) < 2:
        return fallback

    blocks: list[str] = []
    for label, meals, note in users:
        total = sum(meal.calories for meal in meals)
        formatted = ", ".join(_format_meal(meal) for meal in meals if meal.dish)
        if not formatted:
            continue
        blocks.append(
            f"User: {label}\n"
            f"  Total: {total} kcal\n"
            f"  Meals (chronological): [{formatted}]\n"
            f"  Draft score: {note.health_score}\n"
            f"  Draft summary: {note.summary}"
        )

    if len(blocks) < 2:
        return fallback

    user_prompt = (
        "Calibrate the following users' health scores against each other "
        "according to the system prompt. Return one entry per user.\n\n"
        + "\n\n".join(blocks)
    )

    try:
        raw = await call_responses(
            client,
            model=model,
            system=DAY_RERANK_SYSTEM_PROMPT,
            user=user_prompt,
        )
        return parse_rerank_scores(raw, fallback=fallback)
    except Exception:
        logger.exception("day rerank generation failed")
        return fallback


def _format_meal(meal: Meal) -> str:
    base = f'"{meal.dish}" {meal.calories} kcal'
    eaten_at = (meal.eaten_at or "").strip()
    if eaten_at:
        return f"{base} at {eaten_at}"
    return base
