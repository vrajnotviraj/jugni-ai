from dataclasses import dataclass
from datetime import date, timedelta

# Milestone lengths that earn richer celebratory copy (KTD7).
MILESTONES = (3, 7, 14, 30)

# Hard cap on the backward walk so a pathological history can never loop
# unbounded. The service builds its lookback window from the same constant, so
# this is the single source of truth for "how far back a streak can reach".
LOOKBACK_DAYS = 120


@dataclass(frozen=True, slots=True)
class StreakState:
    length: int
    logged_today: bool
    alive: bool
    milestone: int | None = None


@dataclass(frozen=True, slots=True)
class AtRiskUser:
    """One person whose live streak is in danger because they have not logged
    on the current day yet (used by the evening nudge)."""

    sender_label: str
    streak: int


def compute_streak(active_days: set[str], as_of: str) -> StreakState:
    """Length of the consecutive-day streak ending at ``as_of``.

    Walks backward day by day, counting active days and tolerating a single
    isolated miss; the run breaks at the first *two consecutive* misses
    (never-miss-twice, KTD3). ``active_days`` and ``as_of`` are ISO day-keys in
    one shared clock — no timezone logic lives here.
    """
    as_of_date = date.fromisoformat(as_of)
    logged_today = as_of in active_days

    cursor = as_of_date
    length = 0
    gap_run = 0
    for _ in range(LOOKBACK_DAYS):
        if cursor.isoformat() in active_days:
            length += 1
            gap_run = 0
        else:
            gap_run += 1
            if gap_run == 2:
                break
        cursor -= timedelta(days=1)

    # Alive while the most recent active day is still within grace: either today
    # itself or yesterday. Two misses in a row at the front means it has broken.
    yesterday = (as_of_date - timedelta(days=1)).isoformat()
    alive = logged_today or yesterday in active_days

    milestone = length if logged_today and length in MILESTONES else None
    return StreakState(
        length=length,
        logged_today=logged_today,
        alive=alive,
        milestone=milestone,
    )
