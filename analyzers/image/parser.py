import json

from analyzers.image.prompts import GENERAL_TIP_FALLBACK
from domain.analysis import FoodAnalysis
from llm.json_parsing import parse_fenced_json


class CalorieEstimationError(RuntimeError):
    pass


def parse_food_analysis(raw_text: str) -> FoodAnalysis:
    try:
        payload = parse_fenced_json(raw_text)
    except json.JSONDecodeError as error:
        raise CalorieEstimationError(
            f"OpenAI response was not valid JSON: {raw_text[:200]}"
        ) from error

    calories = payload.get("calories")
    if not isinstance(calories, int) or calories < 0:
        raise CalorieEstimationError(
            "OpenAI response did not include a non-negative integer 'calories'."
        )

    confidence = payload.get("confidence")
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    is_food = bool(payload.get("is_food", True))
    tip = str(payload.get("tip") or "").strip()
    if is_food and not tip:
        tip = GENERAL_TIP_FALLBACK

    return FoodAnalysis(
        dish=str(payload.get("dish") or "Unknown dish"),
        calories=calories,
        confidence=confidence,
        tip=tip,
        is_food=is_food,
    )
