import asyncio
import logging
from zoneinfo import ZoneInfo

from analyzers.summary.factory import DaySummarizer
from core.dates import day_key_for_day_iso, summary_time_context, today_day_key
from domain.breakdown import daily_user_breakdown
from domain.calorie_target import (
    calorie_target,
    goal_summary,
    highlight_macro,
    protein_target_g,
)
from domain.day import DayNote, DayReport, UserDay
from domain.photo import StoredPhoto
from domain.profile import UserProfile
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from workflows.personalization import dietary_facts
from workflows.streak import user_streak

logger = logging.getLogger(__name__)


async def build_day_report(
    *,
    repo: PhotoRepository,
    day_summarizer: DaySummarizer,
    chat_id: int,
    day_iso: str | None,
    timezone: ZoneInfo,
    profile_repo: ProfileRepository | None = None,
) -> DayReport:
    day_key = day_key_for_day_iso(day_iso) if day_iso else today_day_key(timezone)
    photos = await repo.estimated_photos_for_day(chat_id=chat_id, day_key=day_key)
    sender_ids = _sender_ids_by_label(photos)
    # Resolve each sender's profile once, up front: it drives their timezone (for
    # both meal-time display and the note's clock), goal, and calorie target.
    # Loading here avoids a second per-user fetch inside _note_for_user.
    labels = list(dict.fromkeys(photo.sender_label for photo in photos))
    loaded = await asyncio.gather(
        *(_load_profile(sender_ids.get(label), profile_repo) for label in labels)
    )
    profiles = dict(zip(labels, loaded, strict=True))
    zones = {
        label: (profile.zone(timezone) if profile else timezone)
        for label, profile in profiles.items()
    }
    users = daily_user_breakdown(photos, timezone=timezone, zones=zones)
    logger.info(
        "summary chat=%s day=%s photos=%s users=%s",
        chat_id,
        day_key,
        len(photos),
        len(users),
    )

    results = await asyncio.gather(
        *(
            _note_for_user(
                user,
                sender_id=sender_ids.get(user.sender_label),
                profile=profiles.get(user.sender_label),
                zone=zones.get(user.sender_label, timezone),
                profile_repo=profile_repo,
                day_summarizer=day_summarizer,
                day_key=day_key,
            )
            for user in users
        )
    )

    # Streak is display-only: computed per ranked user but never a ranking key.
    # A single failing user_streak must not break the whole report, so we gather
    # with return_exceptions and fall back to a zero-length streak on error.
    streak_results = await asyncio.gather(
        *(
            user_streak(
                repo=repo,
                chat_id=chat_id,
                sender_label=user.sender_label,
                as_of_day_key=day_key,
            )
            for user in users
        ),
        return_exceptions=True,
    )
    streak_lengths = []
    for user, state in zip(users, streak_results, strict=True):
        if isinstance(state, BaseException):
            logger.warning(
                "streak failed chat=%s user=%s err=%s",
                chat_id,
                user.sender_label,
                state,
            )
            streak_lengths.append(0)
        else:
            streak_lengths.append(state.length)

    return DayReport.assemble(
        chat_id,
        day_key,
        users,
        [note for note, _, _, _ in results],
        total_photos=len(photos),
        calorie_targets=[target for _, target, _, _ in results],
        highlight_macros=[highlight for _, _, highlight, _ in results],
        streaks=streak_lengths,
        protein_targets=[protein for _, _, _, protein in results],
    )


async def _note_for_user(
    user: UserDay,
    *,
    sender_id: int | None,
    profile: UserProfile | None,
    zone: ZoneInfo,
    profile_repo: ProfileRepository | None,
    day_summarizer: DaySummarizer,
    day_key: str,
) -> tuple[DayNote, int | None, str | None, int | None]:
    # The profile (resolved once by the caller) gives the user's clock (R14), a
    # goal-with-target phrase for the note, and a calorie target for ranking.
    # ``zone`` is already the user's timezone, or the app default as a fallback.
    # Compute the target once and reuse it for both the goal phrase and ranking.
    target = calorie_target(profile)
    goal = goal_summary(profile, target)
    # The protein target feeds the note's protein-progress read and the report's
    # per-user protein gauge; None (no weight on file) just omits both.
    protein_target = protein_target_g(profile)
    # The macro to emphasise in the summary's macro line, from the raw goal text.
    macro_highlight = highlight_macro(profile.goal if profile else None)
    dietary = await dietary_facts(profile, profile_repo, sender_id)
    time_context = summary_time_context(day_key, zone)
    logger.info(
        "summary note user=%s sender_id=%s tz=%s goal=%r target=%s "
        "dietary_chars=%s meals=%s",
        user.sender_label,
        sender_id,
        zone.key,
        goal,
        target,
        len(dietary) if dietary else 0,
        len(user.meals),
    )
    note = await day_summarizer(
        list(user.meals),
        as_of=time_context,
        goal=goal,
        dietary=dietary,
        protein_target=protein_target,
    )
    return note, target, macro_highlight, protein_target


async def _load_profile(
    sender_id: int | None,
    profile_repo: ProfileRepository | None,
):
    if profile_repo is None or sender_id is None:
        return None
    return await profile_repo.get_profile(sender_id)


def _sender_ids_by_label(photos: list[StoredPhoto]) -> dict[str, int]:
    """Best-effort map of sender_label to sender_id from the day's photos.

    The link is one-directional and lossy: senderless photos carry no id, so a
    user whose photos all lack one simply falls back to the app timezone.
    """
    mapping: dict[str, int] = {}
    for photo in photos:
        if photo.sender_id is not None and photo.sender_label not in mapping:
            mapping[photo.sender_label] = photo.sender_id
    return mapping
