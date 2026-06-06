from dataclasses import dataclass, field

# Meal-period windows by local hour: breakfast < 11:00, lunch 11:00-16:59,
# dinner >= 17:00. Used to measure how complete a logged day is.
_BREAKFAST_END = 11
_LUNCH_END = 17


@dataclass(frozen=True, slots=True)
class Meal:
    dish: str
    calories: int
    eaten_at: str
    protein_g: int = 0
    carb_g: int = 0
    fat_g: int = 0
    fibre_g: int = 0
    added_sugar_g: int = 0
    sat_fat_g: int = 0


@dataclass(frozen=True, slots=True)
class DayMacros:
    protein_g: int = 0
    carb_g: int = 0
    fat_g: int = 0
    fibre_g: int = 0
    added_sugar_g: int = 0
    sat_fat_g: int = 0

    @classmethod
    def from_meals(cls, meals: "tuple[Meal, ...] | list[Meal]") -> "DayMacros":
        totals = cls()
        for meal in meals:
            totals = cls(
                protein_g=totals.protein_g + meal.protein_g,
                carb_g=totals.carb_g + meal.carb_g,
                fat_g=totals.fat_g + meal.fat_g,
                fibre_g=totals.fibre_g + meal.fibre_g,
                added_sugar_g=totals.added_sugar_g + meal.added_sugar_g,
                sat_fat_g=totals.sat_fat_g + meal.sat_fat_g,
            )
        return totals


def _meal_hour(eaten_at: str | None) -> int | None:
    text = (eaten_at or "").strip()
    if ":" not in text:
        return None
    try:
        return int(text.split(":", 1)[0])
    except ValueError:
        return None


def meal_period_flags(meals: "tuple[Meal, ...] | list[Meal]") -> dict[str, bool]:
    flags = {"breakfast": False, "lunch": False, "dinner": False}
    for meal in meals:
        if not meal.dish:
            continue
        hour = _meal_hour(meal.eaten_at)
        if hour is None:
            continue
        if hour < _BREAKFAST_END:
            flags["breakfast"] = True
        elif hour < _LUNCH_END:
            flags["lunch"] = True
        else:
            flags["dinner"] = True
    return flags


def meal_periods_covered(meals: "tuple[Meal, ...] | list[Meal]") -> int:
    return sum(meal_period_flags(meals).values())


def _calorie_distance(user: "UserDaySummary") -> int:
    # Closer to the person's realistic calorie target ranks higher. Without a
    # target (no profile or no weight) keep the old "lower calories first" rule.
    if user.calorie_target is None:
        return user.calories
    return abs(user.calories - user.calorie_target)


@dataclass(frozen=True, slots=True)
class UserDay:
    sender_label: str
    calories: int
    meals: tuple[Meal, ...]

    @property
    def macros(self) -> DayMacros:
        return DayMacros.from_meals(self.meals)


@dataclass(frozen=True, slots=True)
class DayNote:
    summary: str
    health_score: int


@dataclass(frozen=True, slots=True)
class MealTimeline:
    time: str
    dish: str
    calories: int


@dataclass(frozen=True, slots=True)
class UserDaySummary:
    sender_label: str
    calories: int
    dishes: tuple[str, ...]
    meals_timeline: tuple[MealTimeline, ...]
    summary: str
    health_score: int
    rank: int
    meal_periods_covered: int = 0
    calorie_target: int | None = None
    # Daily protein target in grams (see domain.calorie_target.protein_target_g),
    # or None when the person has no weight on file. Display-only.
    protein_target_g: int | None = None
    macros: DayMacros = field(default_factory=DayMacros)
    # Label of the macro to emphasise for this person's goal (see
    # domain.calorie_target.highlight_macro), or None when none stands out.
    highlight_macro: str | None = None
    # Current logging-streak length (display-only; never a ranking key in v1).
    streak: int = 0


@dataclass(frozen=True, slots=True)
class DayReport:
    chat_id: int
    day_key: str
    total_photos: int
    users: tuple[UserDaySummary, ...]

    @classmethod
    def assemble(
        cls,
        chat_id: int,
        day_key: str,
        users: list[UserDay],
        notes: list[DayNote],
        total_photos: int,
        calorie_targets: list[int | None] | None = None,
        highlight_macros: list[str | None] | None = None,
        streaks: list[int] | None = None,
        protein_targets: list[int | None] | None = None,
    ) -> "DayReport":
        # Build per-user summaries, carrying meal-period coverage alongside each
        # for a hard two-tier ranking.
        targets = calorie_targets or [None] * len(users)
        highlights = highlight_macros or [None] * len(users)
        streak_lengths = streaks or [0] * len(users)
        protein = protein_targets or [None] * len(users)
        summaries: list[UserDaySummary] = []
        for user, note, target, highlight, streak, protein_target in zip(
            users, notes, targets, highlights, streak_lengths, protein, strict=True
        ):
            dishes = tuple(meal.dish for meal in user.meals if meal.dish)
            timeline = tuple(
                MealTimeline(
                    time=meal.eaten_at or "",
                    dish=meal.dish,
                    calories=meal.calories,
                )
                for meal in user.meals
                if meal.dish
            )
            summaries.append(
                UserDaySummary(
                    sender_label=user.sender_label,
                    calories=user.calories,
                    dishes=dishes,
                    meals_timeline=timeline,
                    summary=note.summary,
                    health_score=note.health_score,
                    rank=0,
                    meal_periods_covered=meal_periods_covered(user.meals),
                    calorie_target=target,
                    protein_target_g=protein_target,
                    macros=user.macros,
                    highlight_macro=highlight,
                    streak=streak,
                )
            )

        # Hard two-tier rank: meal-period coverage first (3 > 2 > 1 > 0), then
        # health score within each tier. An honest 3-meal day always beats any
        # 2-meal day, regardless of score — this is the product's game-theory
        # intent: reward logging breakfast, lunch, AND dinner. The next tiebreak
        # is calorie-target adherence (closest to the person's realistic target
        # wins); without a target it falls back to lower-calories-first. Alphabetical
        # sender_label keeps the order deterministic.
        summaries.sort(
            key=lambda u: (
                -u.meal_periods_covered,
                -u.health_score,
                _calorie_distance(u),
                u.sender_label.removeprefix("@").casefold(),
            )
        )
        ranked = tuple(
            UserDaySummary(
                sender_label=u.sender_label,
                calories=u.calories,
                dishes=u.dishes,
                meals_timeline=u.meals_timeline,
                summary=u.summary,
                health_score=u.health_score,
                rank=index,
                meal_periods_covered=u.meal_periods_covered,
                calorie_target=u.calorie_target,
                protein_target_g=u.protein_target_g,
                macros=u.macros,
                highlight_macro=u.highlight_macro,
                streak=u.streak,
            )
            for index, u in enumerate(summaries, start=1)
        )

        return cls(
            chat_id=chat_id,
            day_key=day_key,
            total_photos=total_photos,
            users=ranked,
        )
