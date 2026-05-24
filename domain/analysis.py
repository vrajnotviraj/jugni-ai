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
