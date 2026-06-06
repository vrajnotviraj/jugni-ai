"""Assemble the deterministic envelope for a /recommend request.

Everything the recommender prompt may state as fact is computed here: today's
totals, gaps, targets, history-derived preference signals, and the time/slot
read. The group surface never receives weight-invertible numbers (raw targets,
absolute remaining budget) — privacy by construction, not prompt instruction.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from core.dates import DAY_OVER_HOUR, next_meal_slot, recent_day_keys, today_day_key
from domain.calorie_target import calorie_target, goal_summary, protein_target_g
from domain.day import DayMacros
from domain.photo import StoredPhoto
from domain.recommendation import (
    MIN_MEAL_KCAL,
    MealRecommendationContext,
    macro_gaps,
    preference_signals,
)
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from workflows.personalization import dietary_facts

logger = logging.getLogger(__name__)

# How many past eating days feed the preference signals.
HISTORY_DAYS = 10


async def build_recommendation_context(
    *,
    user_id: int,
    sender_label: str,
    surface: str,
    slot: str | None,
    modifier: str | None,
    repo: PhotoRepository,
    profile_repo: ProfileRepository,
    chat_id: int | None,
    timezone: ZoneInfo,
) -> MealRecommendationContext:
    """Build the recommendation context for one user.

    ``chat_id`` is the group chat holding the meal history (the command's own
    chat on the group surface, the first allowed group for a DM); ``None``
    means no history source at all, which degrades to a profile-only context.
    """
    profile = await profile_repo.get_profile(user_id)
    zone = profile.zone(timezone) if profile else timezone
    today_key = today_day_key(zone)

    today, history = await _user_meals(
        repo, chat_id=chat_id, user_id=user_id,
        sender_label=sender_label, today_key=today_key,
    )

    today_calories = sum(photo.calories for photo in today)
    macros = DayMacros(
        protein_g=sum(p.protein_g for p in today),
        carb_g=sum(p.carb_g for p in today),
        fat_g=sum(p.fat_g for p in today),
        fibre_g=sum(p.fibre_g for p in today),
        added_sugar_g=sum(p.added_sugar_g for p in today),
        sat_fat_g=sum(p.sat_fat_g for p in today),
    )

    target = calorie_target(profile)
    protein_target = protein_target_g(profile)
    protein_pct = (
        round(macros.protein_g / protein_target * 100) if protein_target else None
    )
    gaps = macro_gaps(macros, today_calories, protein_target)

    explicit_slot = slot is not None
    resolved_slot = slot or next_meal_slot(zone)

    dietary = await dietary_facts(profile, profile_repo, user_id)
    history_dishes = [p.dish for p in history if p.dish]

    is_group = surface == "group"
    logger.info(
        "recommend context user=%s surface=%s slot=%s today_meals=%s history=%s",
        user_id, surface, resolved_slot, len(today), len(history_dishes),
    )
    return MealRecommendationContext(
        surface=surface,
        slot=resolved_slot,
        modifier=modifier,
        time_context=_time_line(zone, resolved_slot, explicit=explicit_slot),
        # The group surface gets the goal's direction in the user's own words,
        # never the derived calorie figure goal_summary appends.
        goal=(profile.goal if profile else None)
        if is_group
        else goal_summary(profile, target),
        dietary=dietary,
        today_meals=_format_meals(today, zone),
        today_calories=today_calories,
        macros=macros,
        gaps=gaps,
        preferences=preference_signals(history_dishes),
        has_history=bool(history_dishes),
        # Weight-invertible numbers never enter a group-surface context.
        calorie_target=None if is_group else target,
        protein_target_g=None if is_group else protein_target,
        remaining_kcal=None if is_group else _remaining(target, today_calories),
        protein_pct=protein_pct,
    )


async def _user_meals(
    repo: PhotoRepository,
    *,
    chat_id: int | None,
    user_id: int,
    sender_label: str,
    today_key: str,
) -> tuple[list[StoredPhoto], list[StoredPhoto]]:
    """One user's (today, recent-history) meals from the group's stored photos.

    Selection is by stable sender_id first; the display-label fallback applies
    only to senderless photos and only while the label is unambiguous across
    the whole range — a label claimed by another member yields no match rather
    than a guess (two members named "Raj" must never read each other's meals).
    """
    if chat_id is None:
        return [], []
    day_keys = recent_day_keys(today_key, HISTORY_DAYS + 1)
    by_day = await repo.estimated_photos_for_range(chat_id=chat_id, day_keys=day_keys)

    label_claimed_by_other = any(
        p.sender_id not in (None, user_id) and p.sender_label == sender_label
        for photos in by_day.values()
        for p in photos
    )

    def mine(photo: StoredPhoto) -> bool:
        if photo.sender_id is not None:
            return photo.sender_id == user_id
        return photo.sender_label == sender_label and not label_claimed_by_other

    today = [p for p in by_day.get(today_key, []) if mine(p)]
    history = [
        p
        for day, photos in by_day.items()
        if day != today_key
        for p in photos
        if mine(p)
    ]
    return today, history


def _remaining(target: int | None, consumed: int) -> int | None:
    """Calories left in the day's budget, floored so the framing is always
    "something sensible to eat", never a shrinking-to-zero number (R16)."""
    if target is None:
        return None
    return max(MIN_MEAL_KCAL, target - consumed)


def _time_line(zone: ZoneInfo, slot: str, *, explicit: bool) -> str:
    """The clock context for the prompt; never contradicts an explicit ask (R17)."""
    now = datetime.now(zone)
    line = f"It is {now.strftime('%H:%M')} in the person's local time."
    if explicit:
        return (
            f"{line} They explicitly asked for a {slot} suggestion; "
            "honour it at this hour."
        )
    if slot == "breakfast" and now.hour >= DAY_OVER_HOUR:
        return (
            f"{line} The eating day is winding down, so this plans "
            "tomorrow's breakfast."
        )
    return f"{line} The natural next meal is {slot}."


def _format_meals(photos: list[StoredPhoto], zone: ZoneInfo) -> str:
    parts = []
    for p in photos:
        if not p.dish:
            continue
        time_label = p.sent_at.astimezone(zone).strftime("%H:%M ") if p.sent_at else ""
        parts.append(f"{time_label}{p.dish} ({p.calories} kcal)")
    return "; ".join(parts)
