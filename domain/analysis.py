from dataclasses import dataclass
from typing import Literal

Confidence = Literal["high", "medium", "low"]
CONFIDENCE_LEVELS: frozenset[str] = frozenset(("high", "medium", "low"))


@dataclass(frozen=True, slots=True)
class FoodAnalysis:
    dish: str
    calories: int
    confidence: Confidence
    tip: str
    is_food: bool
    protein_g: int = 0
    carb_g: int = 0
    fat_g: int = 0
    fibre_g: int = 0
    added_sugar_g: int = 0
    sat_fat_g: int = 0
    # The per-item breakdown behind the calorie total (e.g. "2 rotli ~160",
    # "dal katori ~190"), shown to the user so the number is transparent.
    items: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MealExtraction:
    items: tuple[str, ...]
    is_food: bool
    dish: str
    calories: int
    confidence: Confidence
    protein_g: int = 0
    carb_g: int = 0
    fat_g: int = 0
    fibre_g: int = 0
    added_sugar_g: int = 0
    sat_fat_g: int = 0


@dataclass(frozen=True, slots=True)
class CoachingTip:
    tip: str
