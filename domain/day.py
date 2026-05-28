from dataclasses import dataclass

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
    ) -> "DayReport":
        # Build per-user summaries, carrying meal-period coverage alongside each
        # so the ranking can break score ties in favour of more complete days.
        enriched: list[tuple[UserDaySummary, int]] = []
        for user, note in zip(users, notes, strict=True):
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
            summary = UserDaySummary(
                sender_label=user.sender_label,
                calories=user.calories,
                dishes=dishes,
                meals_timeline=timeline,
                summary=note.summary,
                health_score=note.health_score,
                rank=0,
            )
            enriched.append((summary, meal_periods_covered(user.meals)))

        # Rank by healthiness — highest score first. On a score tie, the more
        # complete day wins (more meal periods covered) so honest full-day logging
        # is never beaten by a cherry-picked subset. Lower calories then
        # alphabetical sender_label keep the order deterministic.
        enriched.sort(
            key=lambda e: (
                -e[0].health_score,
                -e[1],
                e[0].calories,
                e[0].sender_label.removeprefix("@").casefold(),
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
            )
            for index, (u, _periods) in enumerate(enriched, start=1)
        )

        return cls(
            chat_id=chat_id,
            day_key=day_key,
            total_photos=total_photos,
            users=ranked,
        )
