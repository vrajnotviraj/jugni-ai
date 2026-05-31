from core.dates import recent_day_keys
from domain.streak import LOOKBACK_DAYS, StreakState, compute_streak
from storage.photo_repository import PhotoRepository


async def user_streak(
    *,
    repo: PhotoRepository,
    chat_id: int,
    sender_label: str,
    as_of_day_key: str,
) -> StreakState:
    """One user's streak as of ``as_of_day_key`` (already an app-timezone key).

    The service owns the lookback window; the domain owns the never-miss-twice
    rule. ``as_of_day_key`` is produced by callers via the existing day-key
    helpers, so all three surfaces share one clock (KTD6, KTD9).
    """
    day_keys = recent_day_keys(as_of_day_key, LOOKBACK_DAYS)
    active = await repo.user_active_days(
        chat_id=chat_id, sender_label=sender_label, day_keys=day_keys
    )
    return compute_streak(active, as_of_day_key)
