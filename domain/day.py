from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Meal:
    dish: str
    calories: int
    eaten_at: str


@dataclass(frozen=True, slots=True)
class UserDay:
    sender_label: str
    calories: int
    meals: tuple[Meal, ...]


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
        # Build per-user summaries from parallel lists (zip preserves alignment).
        summaries: list[UserDaySummary] = []
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
            summaries.append(
                UserDaySummary(
                    sender_label=user.sender_label,
                    calories=user.calories,
                    dishes=dishes,
                    meals_timeline=timeline,
                    summary=note.summary,
                    health_score=note.health_score,
                    rank=0,
                )
            )

        # Rank by healthiness — highest score first. Tiebreak by lower calories,
        # then alphabetically by sender_label so the order is deterministic.
        summaries.sort(
            key=lambda u: (
                -u.health_score,
                u.calories,
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
            )
            for index, u in enumerate(summaries, start=1)
        )

        return cls(
            chat_id=chat_id,
            day_key=day_key,
            total_photos=total_photos,
            users=ranked,
        )
