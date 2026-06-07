"""Typed objects and pure rules for /recommend meal suggestions.

The deterministic envelope: code computes today's gap flags and a rule-based
fallback; the LLM only chooses and explains inside it ("LLM perceives, code
grades"). Nothing here does I/O.
"""

from dataclasses import dataclass

from domain.day import DayMacros
from domain.scoring import (
    _ADDED_SUGAR_BAD_PCT,
    _FIBRE_TARGET_G,
    _PROTEIN_TARGET_G,
    _SAT_FAT_BAD_PCT,
)

MEAL_SLOTS = ("breakfast", "lunch", "dinner", "snack")

# Remaining-budget framing never drops below a sensible per-meal floor, so a
# person who already ate past their target is steered toward something light,
# never toward eating nothing (R16).
MIN_MEAL_KCAL = 300


@dataclass(frozen=True, slots=True)
class RecommendedMealOption:
    title: str
    calorie_range: str
    why: str


@dataclass(frozen=True, slots=True)
class MealRecommendationResult:
    because_today: str
    options: tuple[RecommendedMealOption, ...]
    recipe_video_url: str = ""
    is_fallback: bool = False


@dataclass(frozen=True, slots=True)
class MealRecommendationContext:
    """Everything the recommender prompt may state as fact, precomputed in code.

    ``surface`` enforces group privacy by construction: the builder never sets
    ``calorie_target``/``remaining_kcal`` (both weight-invertible) for the
    group surface, so they cannot leak into a group prompt.
    """

    surface: str  # "dm" | "group"
    slot: str  # one of MEAL_SLOTS
    slot_is_explicit: bool
    user_request: str
    time_context: str
    goal: str | None
    dietary: str | None
    today_meals: str  # formatted "HH:MM dish (kcal)" list, "" when none
    today_calories: int
    macros: DayMacros
    gaps: tuple[str, ...]
    calorie_target: int | None = None  # DM only
    remaining_kcal: int | None = None  # DM only
    protein_pct: int | None = None  # % of protein target met; group-safe


# --- Gap rules ----------------------------------------------------------- #

# Priority order is the append order below: protein first (the audience's
# research-confirmed weak spot), then fibre, then the two "already high" flags.
_GAP_PHRASES = {
    "protein": "protein still has room today",
    "fibre": "fibre has been light today",
    "sugar": "added sugar has already run high today",
    "satfat": "heavy or fried fat has already run high today",
}


def macro_gaps(
    macros: DayMacros,
    calories: int,
    protein_target: int | None = None,
) -> tuple[str, ...]:
    """Priority-ordered gap/excess flags for the day so far.

    Pure arithmetic over precomputed totals; safe on zero-meal days and
    ``None`` targets (the scoring-rubric anchors fill in).
    """
    gaps: list[str] = []
    if macros.protein_g < (protein_target or _PROTEIN_TARGET_G):
        gaps.append("protein")
    if macros.fibre_g < _FIBRE_TARGET_G:
        gaps.append("fibre")
    if calories > 0:
        if (macros.added_sugar_g * 4) / calories > _ADDED_SUGAR_BAD_PCT:
            gaps.append("sugar")
        if (macros.sat_fat_g * 9) / calories > _SAT_FAT_BAD_PCT:
            gaps.append("satfat")
    return tuple(gaps)


def gap_phrases(gaps: tuple[str, ...]) -> str:
    """The gap flags as plain words for the prompt and fallback lead line."""
    return "; ".join(_GAP_PHRASES[gap] for gap in gaps if gap in _GAP_PHRASES)


# --- Rule-based fallback (R18) -------------------------------------------- #

# Safe, broadly liked meals per slot, protein-forward options first so a
# protein gap is served by default. Deliberately no sweets or added-sugar
# items anywhere (a fallback must be safe on a high-sugar day), and dietary
# facts filter the rest. Calorie figures are honest ranges, never precise.
_FALLBACK_TABLE: dict[str, tuple[RecommendedMealOption, ...]] = {
    "breakfast": (
        RecommendedMealOption(
            "Besan chilla with mint chutney",
            "~250-350 kcal",
            "A familiar savoury start that gets real protein in early.",
        ),
        RecommendedMealOption(
            "Egg bhurji with whole-wheat roti",
            "~300-400 kcal",
            "Eggs make an easy protein anchor for the morning.",
        ),
        RecommendedMealOption(
            "Oats cooked in milk with nuts and seeds",
            "~300-400 kcal",
            "Whole grains and dairy cover fibre and protein together.",
        ),
        RecommendedMealOption(
            "Poha with peanuts and sprouts",
            "~300-400 kcal",
            "The sprouts and peanuts lift an everyday breakfast's protein.",
        ),
    ),
    "lunch": (
        RecommendedMealOption(
            "Dal, roti, sabzi and a side salad",
            "~450-600 kcal",
            "The classic complete plate: pulse, grain, vegetable.",
        ),
        RecommendedMealOption(
            "Paneer bhurji with whole-wheat roti and kachumber",
            "~450-600 kcal",
            "Paneer carries the protein while the salad adds crunch and fibre.",
        ),
        RecommendedMealOption(
            "Grilled chicken with rice and salad",
            "~450-600 kcal",
            "A lean protein anchor that keeps the plate light.",
        ),
        RecommendedMealOption(
            "Rajma chawal with kachumber",
            "~500-650 kcal",
            "Rajma makes a filling, protein-fair lunch with fresh crunch.",
        ),
    ),
    "dinner": (
        RecommendedMealOption(
            "Moong dal khichdi with a lauki sabzi",
            "~400-550 kcal",
            "Gentle on a full day while still landing protein and fibre.",
        ),
        RecommendedMealOption(
            "Paneer and vegetable stir-fry with roti",
            "~400-550 kcal",
            "Paneer plus vegetables keeps dinner light but substantial.",
        ),
        RecommendedMealOption(
            "Grilled fish with sauteed vegetables",
            "~350-500 kcal",
            "A light protein-led dinner that sits easy late in the day.",
        ),
        RecommendedMealOption(
            "Dal with jeera rice and a side salad",
            "~450-600 kcal",
            "A steady pulse-and-grain dinner with fibre from the salad.",
        ),
    ),
    "snack": (
        RecommendedMealOption(
            "Sprouts chaat with onion, tomato and lemon",
            "~150-250 kcal",
            "A fresh, crunchy snack that quietly adds protein.",
        ),
        RecommendedMealOption(
            "Boiled eggs with a pinch of chaat masala",
            "~150-200 kcal",
            "The simplest protein top-up between meals.",
        ),
        RecommendedMealOption(
            "Roasted chana with a glass of chaas",
            "~150-250 kcal",
            "Crunchy, familiar, and far better company than a biscuit.",
        ),
        RecommendedMealOption(
            "A bowl of fruit with a handful of nuts",
            "~150-250 kcal",
            "Whole fruit and nuts cover the sweet craving the honest way.",
        ),
    ),
}

# Foods a dietary fact can rule out, matched as words inside option titles.
_FILTERABLE_FOODS = ("egg", "chicken", "fish", "paneer", "curd", "milk", "chaas")
_NON_VEG_FOODS = ("egg", "chicken", "fish")
_DAIRY_FOODS = ("paneer", "curd", "milk", "chaas")


def _excluded_foods(dietary: str | None) -> set[str]:
    text = (dietary or "").casefold().replace("-", " ")
    excluded: set[str] = set()
    # vegetarian, veg, vegan, jain — but not "non veg"/"non-vegetarian".
    if ("veg" in text and "non veg" not in text) or "jain" in text:
        excluded.update(_NON_VEG_FOODS)
    if "vegan" in text:
        excluded.update(_DAIRY_FOODS)
    for food in _FILTERABLE_FOODS:
        if f"no {food}" in text:
            excluded.add(food)
    return excluded


def fallback_recommendation(
    context: MealRecommendationContext,
) -> MealRecommendationResult:
    """Deterministic safe options when the LLM output is unusable (R18).

    Filters the slot's table against dietary facts and returns 2-3 options;
    the table is large enough that even a vegan filter leaves two.
    """
    excluded = _excluded_foods(context.dietary)
    options = tuple(
        option
        for option in _FALLBACK_TABLE[context.slot]
        if not any(food in option.title.casefold() for food in excluded)
    )[:3]
    because = gap_phrases(context.gaps) or "a fresh read of the day"
    return MealRecommendationResult(
        because_today=f"Going by the basics today: {because}.",
        options=options,
        is_fallback=True,
    )
