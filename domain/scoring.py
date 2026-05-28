from dataclasses import dataclass

from domain.day import DayMacros, Meal, _meal_hour

# Diet-quality rubric (HEI-2020-inspired): the day's 1-10 health score is a
# deterministic function of food-group signals + macro totals + meal timing.
# Completeness (how many meal periods the user logged) is NOT capped here —
# it is the primary ranking key in domain.day.DayReport.assemble, so a great
# 1-meal day at score 9 still ranks below an honest 3-meal day at score 4.
#
# Rubric (max 100 → mapped to 1-10):
#   food-group adequacy   max 40
#   food-group moderation max 25
#   timing                max  5
#   macro adequacy        max 20  (protein + fibre)
#   macro moderation      max 10  (added sugar % kcal + sat fat % kcal)

# Timing thresholds.
_BREAKFAST_LATEST = 11
_DINNER_LATEST = 21
_EATING_WINDOW_HOURS = 12

# Macro adequacy targets (grams/day, sized for ~1500-2200 kcal adult intake).
_PROTEIN_TARGET_G = 60
_PROTEIN_PARTIAL_G = 40
_FIBRE_TARGET_G = 25
_FIBRE_PARTIAL_G = 15

# Macro moderation ceilings (% of total kcal). WHO + HEI thresholds.
_ADDED_SUGAR_BAD_PCT = 0.10
_ADDED_SUGAR_WARN_PCT = 0.05
_SAT_FAT_BAD_PCT = 0.10
_SAT_FAT_WARN_PCT = 0.07


@dataclass(frozen=True, slots=True)
class FoodSignals:
    """Food-group signals detected by the LLM. Scoring math is done here, in
    code, not by the model — the model only perceives what is on the plate."""

    veg_servings: int = 0
    has_legume: bool = False
    has_whole_grain: bool = False
    protein_meals: int = 0
    has_fruit: bool = False
    has_plain_dairy: bool = False
    fried_items: int = 0
    sweet_items: int = 0
    ultraprocessed_items: int = 0
    refined_grain_dominant: bool = False


def compute_day_score(
    signals: FoodSignals,
    meals: list[Meal],
    macros: DayMacros | None = None,
) -> int:
    macros = macros or DayMacros.from_meals(meals)
    kcal = sum(meal.calories for meal in meals)

    quality = (
        _adequacy_points(signals)
        + _moderation_points(signals)
        + _timing_points(meals)
    )
    if _has_macro_data(meals):
        quality += _macro_adequacy_points(macros)
        quality += _macro_moderation_points(macros, kcal)
    else:
        # Legacy/zero-macro day: macros were never estimated. Give a neutral
        # mid-range contribution so the day is not punished for missing data
        # rather than for actually unbalanced eating.
        quality += 15
    return max(1, round(quality / 10))


def _has_macro_data(meals: list[Meal]) -> bool:
    return any(
        meal.protein_g or meal.carb_g or meal.fat_g or meal.fibre_g
        for meal in meals
    )


def _adequacy_points(s: FoodSignals) -> int:
    points = 0
    points += 12 if s.veg_servings >= 2 else 6 if s.veg_servings == 1 else 0
    points += 8 if s.has_legume else 0
    points += 8 if s.has_whole_grain else 0
    points += 8 if s.protein_meals >= 2 else 4 if s.protein_meals == 1 else 0
    points += 4 if s.has_fruit else 0
    return points  # max 40


def _moderation_points(s: FoodSignals) -> int:
    points = 25
    points -= 12 if s.fried_items >= 2 else 6 if s.fried_items == 1 else 0
    points -= 12 if s.sweet_items >= 2 else 6 if s.sweet_items == 1 else 0
    points -= min(s.ultraprocessed_items, 3) * 3
    if s.refined_grain_dominant and not s.has_whole_grain:
        points -= 4
    return max(0, points)  # max 25


def _timing_points(meals: list[Meal]) -> int:
    hours = sorted(h for h in (_meal_hour(m.eaten_at) for m in meals) if h is not None)
    if not hours:
        return 0
    points = 0
    if hours[0] < _BREAKFAST_LATEST:
        points += 2
    if hours[-1] < _DINNER_LATEST:
        points += 2
    if hours[-1] - hours[0] <= _EATING_WINDOW_HOURS:
        points += 1
    return points  # max 5


def _macro_adequacy_points(macros: DayMacros) -> int:
    points = 0
    if macros.protein_g >= _PROTEIN_TARGET_G:
        points += 10
    elif macros.protein_g >= _PROTEIN_PARTIAL_G:
        points += 5
    if macros.fibre_g >= _FIBRE_TARGET_G:
        points += 10
    elif macros.fibre_g >= _FIBRE_PARTIAL_G:
        points += 5
    return points  # max 20


def _macro_moderation_points(macros: DayMacros, kcal: int) -> int:
    if kcal <= 0:
        # No food data — moderation cannot be evaluated; give the neutral
        # midpoint so a missing-data day is not punished against a real day.
        return 5

    points = 10
    added_sugar_pct = (macros.added_sugar_g * 4) / kcal
    sat_fat_pct = (macros.sat_fat_g * 9) / kcal

    if added_sugar_pct > _ADDED_SUGAR_BAD_PCT:
        points -= 5
    elif added_sugar_pct > _ADDED_SUGAR_WARN_PCT:
        points -= 2

    if sat_fat_pct > _SAT_FAT_BAD_PCT:
        points -= 5
    elif sat_fat_pct > _SAT_FAT_WARN_PCT:
        points -= 2

    return max(0, points)  # max 10
