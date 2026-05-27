from dataclasses import dataclass

from domain.day import Meal, _meal_hour, meal_period_flags

# Completeness cap (decathlon model): a day cannot reach the top scores unless
# the person ate and logged across all three meal periods. One great meal must
# not win the leaderboard.
_PERIOD_CAP = {0: 1, 1: 4, 2: 7, 3: 10}

# Adequacy floors: protein and vegetables are non-negotiable. A day that skips
# either fundamental cannot score as if it were complete, no matter how "clean"
# (the absence of fried/sweet food must not reward a bland, empty day).
_NO_PROTEIN_CAP = 4
_NO_VEG_CAP = 7

# Late-evening cutoff for the timing bonus.
_LATE_HOUR = 21
_EATING_WINDOW_HOURS = 12


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


def compute_day_score(signals: FoodSignals, meals: list[Meal]) -> int:
    """Map detected food signals + meal timing to a 1-10 health score using a
    diet-quality rubric (adequacy + moderation + timing) capped by completeness.
    """
    quality = (
        _adequacy_points(signals)
        + _moderation_points(signals)
        + _timing_points(meals)
    )
    score = max(1, round(quality / 10))

    periods = sum(meal_period_flags(meals).values())
    cap = _PERIOD_CAP.get(periods, 10)
    if signals.protein_meals == 0:
        cap = min(cap, _NO_PROTEIN_CAP)
    if signals.veg_servings == 0:
        cap = min(cap, _NO_VEG_CAP)
    return min(score, cap)


def _adequacy_points(s: FoodSignals) -> int:
    points = 0
    points += 15 if s.veg_servings >= 2 else 8 if s.veg_servings == 1 else 0
    points += 12 if s.has_legume else 0
    points += 10 if s.has_whole_grain else 0
    points += 12 if s.protein_meals >= 2 else 6 if s.protein_meals == 1 else 0
    points += 6 if s.has_fruit else 0
    points += 5 if s.has_plain_dairy else 0
    return points  # max 60


def _moderation_points(s: FoodSignals) -> int:
    points = 30
    points -= 10 if s.fried_items >= 2 else 4 if s.fried_items == 1 else 0
    points -= 10 if s.sweet_items >= 2 else 4 if s.sweet_items == 1 else 0
    points -= min(s.ultraprocessed_items, 2) * 4
    if s.refined_grain_dominant and not s.has_whole_grain:
        points -= 2
    return max(0, points)  # max 30


def _timing_points(meals: list[Meal]) -> int:
    hours = sorted(h for h in (_meal_hour(m.eaten_at) for m in meals) if h is not None)
    if not hours:
        return 0
    points = 0
    if hours[0] < 11:
        points += 3
    if hours[-1] < _LATE_HOUR:
        points += 3
    if hours[-1] - hours[0] <= _EATING_WINDOW_HOURS:
        points += 2
    if len({m.eaten_at for m in meals if m.dish}) >= 2:
        points += 2
    return points  # max 10
