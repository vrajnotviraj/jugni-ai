from datetime import date, timedelta
from zoneinfo import ZoneInfo

from core.dates import today_day_key
from domain.streak import AtRiskUser
from storage.photo_repository import PhotoRepository
from workflows.streak import user_streak

# Only streaks at least this long are worth an evening nudge — trivial 1-2 day
# runs don't earn a push (protects the notification-fatigue budget, KTD5).
MIN_NUDGE_STREAK = 3


async def build_streak_nudge(
    *,
    repo: PhotoRepository,
    chat_id: int,
    timezone: ZoneInfo,
) -> list[AtRiskUser]:
    """People with a live streak who logged yesterday but not yet today.

    Returns them ordered by streak length (longest first); an empty list means
    nobody is at risk, so the caller sends no message at all.
    """
    today = today_day_key(timezone)
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()

    today_photos = await repo.estimated_photos_for_day(chat_id=chat_id, day_key=today)
    yesterday_photos = await repo.estimated_photos_for_day(
        chat_id=chat_id, day_key=yesterday
    )
    logged_today = {photo.sender_label for photo in today_photos}
    candidates = {photo.sender_label for photo in yesterday_photos} - logged_today

    at_risk: list[AtRiskUser] = []
    for sender_label in candidates:
        state = await user_streak(
            repo=repo,
            chat_id=chat_id,
            sender_label=sender_label,
            as_of_day_key=today,
        )
        if state.alive and state.length >= MIN_NUDGE_STREAK:
            at_risk.append(AtRiskUser(sender_label, state.length))

    at_risk.sort(key=lambda user: (-user.streak, user.sender_label))
    return at_risk
