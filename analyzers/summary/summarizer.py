import logging

from openai import AsyncOpenAI

from analyzers.summary.parser import parse_day_signals
from analyzers.summary.prompts import (
    DAY_SUMMARY_SYSTEM_PROMPT,
    GENERAL_DAY_NOTE_FALLBACK,
)
from domain.day import DayNote, Meal
from domain.scoring import compute_day_score
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)


async def write_day_note(
    client: AsyncOpenAI,
    *,
    model: str,
    meals: list[Meal],
    as_of: str = "",
) -> DayNote:
    if not meals:
        return DayNote(summary="", health_score=0)

    total = sum(meal.calories for meal in meals)
    formatted_meals = ", ".join(_format_meal(meal) for meal in meals if meal.dish)
    if not formatted_meals:
        return DayNote(summary=GENERAL_DAY_NOTE_FALLBACK, health_score=5)

    timing_line = f"Timing context: {as_of} " if as_of else ""
    user_prompt = (
        f"Meals today (chronological): [{formatted_meals}]. Total: {total} kcal. "
        f"{timing_line}"
        "Return the JSON described in the system prompt."
    )

    try:
        raw = await call_responses(
            client,
            model=model,
            system=DAY_SUMMARY_SYSTEM_PROMPT,
            user=user_prompt,
        )
        summary, signals = parse_day_signals(raw)
    except Exception:
        logger.exception("day summary note generation failed")
        return DayNote(summary=GENERAL_DAY_NOTE_FALLBACK, health_score=5)

    return DayNote(summary=summary, health_score=compute_day_score(signals, meals))


def _format_meal(meal: Meal) -> str:
    base = f'"{meal.dish}" {meal.calories} kcal'
    eaten_at = (meal.eaten_at or "").strip()
    if eaten_at:
        return f"{base} at {eaten_at}"
    return base
