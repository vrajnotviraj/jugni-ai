"""Vision extraction: the objective read of the plate (dish, calories, macros).

This half deliberately knows nothing about goals, dietary facts, or coaching --
its only job is to turn a photo into honest numbers. The subjective half lives
in ``analyzers.image.coaching``.
"""

from analyzers.image.extraction.parser import (
    CalorieEstimationError,
    parse_meal_extraction,
)
from analyzers.image.extraction.prompts import (
    FOOD_EXTRACTION_RESPONSE_FORMAT,
    FOOD_EXTRACTION_SYSTEM_PROMPT,
    food_extraction_user_prompt,
)

__all__ = [
    "CalorieEstimationError",
    "FOOD_EXTRACTION_RESPONSE_FORMAT",
    "FOOD_EXTRACTION_SYSTEM_PROMPT",
    "food_extraction_user_prompt",
    "parse_meal_extraction",
]
