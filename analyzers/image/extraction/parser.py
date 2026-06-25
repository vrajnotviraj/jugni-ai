import json

from domain.analysis import CONFIDENCE_LEVELS, MealExtraction
from llm.json_parsing import parse_fenced_json

_MACRO_KEYS = (
    "protein_g",
    "carb_g",
    "fat_g",
    "fibre_g",
    "added_sugar_g",
    "sat_fat_g",
)


class CalorieEstimationError(RuntimeError):
    pass


def parse_meal_extraction(raw_text: str) -> MealExtraction:
    try:
        payload = parse_fenced_json(raw_text)
    except json.JSONDecodeError as error:
        raise CalorieEstimationError(
            f"OpenAI response was not valid extraction JSON: {raw_text[:200]}"
        ) from error
    if not isinstance(payload, dict):
        raise CalorieEstimationError("OpenAI extraction response was not an object.")

    confidence = payload.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        raise CalorieEstimationError(
            "OpenAI response did not include a valid 'confidence'."
        )

    if not bool(payload.get("is_food", True)):
        # Trust the non-food verdict over any stray numbers the model attached:
        # zero the nutrition out rather than rejecting the whole extraction.
        return MealExtraction(
            items=(),
            is_food=False,
            dish=str(payload.get("dish") or "Not food"),
            calories=0,
            confidence=confidence,  # type: ignore[arg-type]
            **{key: 0 for key in _MACRO_KEYS},
        )

    calories = _required_non_negative_int(payload.get("calories"))
    if calories is None:
        raise CalorieEstimationError(
            "OpenAI response did not include a non-negative integer 'calories'."
        )

    macros: dict[str, int] = {}
    for key in _MACRO_KEYS:
        value = _required_non_negative_int(payload.get(key))
        if value is None:
            raise CalorieEstimationError(
                f"OpenAI response did not include a non-negative integer '{key}'."
            )
        macros[key] = value
    if macros["sat_fat_g"] > macros["fat_g"]:
        raise CalorieEstimationError("OpenAI response had sat_fat_g > fat_g.")

    items = payload.get("items") or []
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise CalorieEstimationError("OpenAI response had invalid 'items'.")

    return MealExtraction(
        items=tuple(item.strip() for item in items if item.strip()),
        is_food=True,
        dish=str(payload.get("dish") or "Unknown dish"),
        calories=calories,
        confidence=confidence,  # type: ignore[arg-type]
        **macros,
    )


def _required_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
