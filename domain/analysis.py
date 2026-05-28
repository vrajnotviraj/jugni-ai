from dataclasses import dataclass
from typing import Literal

Confidence = Literal["high", "medium", "low"]


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
