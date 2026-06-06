import logging

from openai import AsyncOpenAI

from analyzers.summary.parser import parse_day_signals
from analyzers.summary.prompts import (
    DAY_SUMMARY_SYSTEM_PROMPT,
    GENERAL_DAY_NOTE_FALLBACK,
)
from domain.day import DayMacros, DayNote, Meal
from domain.scoring import compute_day_score
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)


async def write_day_note(
    client: AsyncOpenAI,
    *,
    model: str,
    meals: list[Meal],
    as_of: str = "",
    goal: str | None = None,
    dietary: str | None = None,
    protein_target: int | None = None,
) -> DayNote:
    if not meals:
        return DayNote(summary="", health_score=0)

    total = sum(meal.calories for meal in meals)
    formatted_meals = ", ".join(_format_meal(meal) for meal in meals if meal.dish)
    if not formatted_meals:
        return DayNote(summary=GENERAL_DAY_NOTE_FALLBACK, health_score=5)

    macros = DayMacros.from_meals(meals)
    # Suppress the macro line when no photos in the day carry macro data
    # (e.g. legacy photos predating the macro-aware photo analyzer). Showing
    # the LLM a row of zeros invites prose that calls out the missing data.
    macro_line = ""
    protein_line = ""
    if any(
        (
            m.protein_g or m.carb_g or m.fat_g
            or m.fibre_g or m.added_sugar_g or m.sat_fat_g
        )
        for m in meals
    ):
        macro_line = (
            f"Macros today: protein {macros.protein_g}g, carb {macros.carb_g}g, "
            f"fat {macros.fat_g}g, fibre {macros.fibre_g}g, added sugar "
            f"{macros.added_sugar_g}g, saturated fat {macros.sat_fat_g}g. "
        )
        # The percentage is computed here, not by the model, so the prose's
        # protein-progress read is always arithmetically honest.
        if protein_target:
            pct = round(macros.protein_g / protein_target * 100)
            protein_line = (
                f"Protein progress: {macros.protein_g}g of about "
                f"{protein_target}g daily target (~{pct}% met). "
            )
    timing_line = f"Timing context: {as_of} " if as_of else ""
    goal_line = f"This person's goal: {goal}. " if goal else ""
    # Dietary notes bound any food the summary suggests; see rule 1c in the prompt.
    dietary = (dietary or "").strip()
    dietary_line = f"Dietary notes: {dietary}. " if dietary else ""
    user_prompt = (
        f"Meals today (chronological): [{formatted_meals}]. Total: {total} kcal. "
        f"{macro_line}"
        f"{protein_line}"
        f"{goal_line}"
        f"{dietary_line}"
        f"{timing_line}"
        "Return the JSON described in the system prompt."
    )

    try:
        raw = await call_responses(
            client,
            model=model,
            system=DAY_SUMMARY_SYSTEM_PROMPT,
            user=user_prompt,
            cache_key="day-summary",
        )
        summary, signals = parse_day_signals(raw)
    except Exception:
        logger.exception("day summary note generation failed")
        return DayNote(summary=GENERAL_DAY_NOTE_FALLBACK, health_score=5)

    return DayNote(
        summary=summary,
        health_score=compute_day_score(signals, meals, macros),
    )


def _format_meal(meal: Meal) -> str:
    base = f'"{meal.dish}" {meal.calories} kcal'
    eaten_at = (meal.eaten_at or "").strip()
    if eaten_at:
        return f"{base} at {eaten_at}"
    return base
