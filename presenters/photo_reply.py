import logging
import random
from html import escape

from domain.analysis import FoodAnalysis
from domain.streak import StreakState
from presenters.macros import macro_shares

logger = logging.getLogger(__name__)

NOT_FOOD_REPLY = "Doesn't look like food. Send a food photo to get a calorie estimate."

PHOTO_REPLY_PARSE_MODE = "HTML"

_CONFIDENCE_ICONS = {"medium": "⚖️", "low": "❓"}


def format_photo_reply(
    sender_label: str,
    analysis: FoodAnalysis,
    daily_total: int,
    streak_line: str | None = None,
    eaten_at: str | None = None,
    calorie_target: int | None = None,
) -> str:
    if not analysis.is_food:
        return NOT_FOOD_REPLY

    header = f"{_dish_icon(analysis.dish)} <b>{escape(sender_label, quote=False)}'s meal</b>"
    dish_line = f"Dish: {escape(analysis.dish, quote=False)}"
    calories_line = f"{_calorie_icon(analysis.calories)} Calories: {analysis.calories} kcal"
    today_line = _today_line(daily_total, calorie_target)
    confidence_line = _confidence_line(analysis.confidence)

    # The message is built as blank-line-separated groups so the streak shout-out
    # gets its own breathing room instead of being wedged between the stats and
    # the confidence line. Within a group the lines stay tight; the blank line
    # only falls between groups.
    identity = [header, dish_line]
    # The eaten-at time is shown only when the caller resolved it (the sender has
    # a timezone set), so the clock is genuinely theirs and not the app default.
    if eaten_at:
        identity.append(f"🕐 Logged at {escape(eaten_at, quote=False)}")

    nutrition = [calories_line]
    try:
        macro_line = _macro_line(analysis)
    except Exception:
        logger.exception("macro line rendering failed; omitting it from the reply")
        macro_line = None
    if macro_line:
        nutrition.append(macro_line)
    nutrition.append(today_line)
    nutrition.append(confidence_line)

    groups = [identity, nutrition]
    if streak_line:
        groups.append([streak_line])

    tip = (analysis.tip or "").strip()
    if tip:
        groups.append([f"<blockquote>{escape(tip, quote=False)}</blockquote>"])

    return "\n\n".join("\n".join(group) for group in groups)


# Milestone copy at 3/7/14/30 (KTD7); other lengths get a quiet count.
_MILESTONE_LINES = {
    3: "🔥 3 days running — habit forming!",
    7: "🎉 Week warrior — 7-day streak!",
    14: "💪 Two weeks straight — 14 days!",
    30: "🏆 30-day streak — legend.",
}

# Rotating copy for the everyday streak line (length >= 2, no milestone) so it
# never reads the same two days running. Every variant names the day count and
# nudges the user to keep going. {n} is the streak length.
_STREAK_LINES = (
    "🔥 {n}-day streak — don't break the chain!",
    "🔥 {n} days in a row — keep it rolling!",
    "🔥 {n}-day streak going strong — log tomorrow too!",
    "🔥 {n} days straight — you're on a roll!",
    "🔥 {n}-day streak! Momentum is yours — keep it up.",
    "🔥 {n} days and counting — don't stop now!",
    "🔥 {n}-day streak — consistency looks good on you!",
    "🔥 {n} days logged in a row — keep the fire alive!",
    "🔥 {n}-day streak — one more day, one more win!",
    "🔥 {n} days deep — the chain is unbroken!",
    "🔥 {n}-day streak — showing up beats perfect. Nice work!",
    "🔥 {n} days running — future you says thanks!",
    "🔥 {n}-day streak — stack another one tomorrow!",
    "🔥 {n} days strong — the habit is forming!",
    "🔥 {n}-day streak — keep showing up!",
    "🔥 {n} days in a row — small wins add up!",
    "🔥 {n}-day streak — don't let it slip tonight!",
    "🔥 {n} days and going — you've got this!",
)


def format_streak_line(state: StreakState) -> str | None:
    """The one-line streak reinforcement, or None when there's nothing to show."""
    if not state.alive or state.length <= 0:
        return None
    if state.milestone in _MILESTONE_LINES:
        return _MILESTONE_LINES[state.milestone]
    if state.length == 1:
        return "🔥 Day 1 — you're on the board!"
    return random.choice(_STREAK_LINES).format(n=state.length)


def _confidence_line(confidence: str) -> str:
    icon = _CONFIDENCE_ICONS.get(confidence)
    prefix = f"{icon} " if icon else ""
    return f"{prefix}Confidence: {confidence}"


def _macro_line(analysis: FoodAnalysis) -> str | None:
    ranked = macro_shares(analysis.protein_g, analysis.carb_g, analysis.fat_g)
    if not ranked:
        return None
    return " · ".join(f"{icon} {label} {pct}%" for label, icon, pct in ranked)


_CALORIE_TIERS = (
    (200, "🌱"),
    (450, "🍴"),
    (750, "⚡"),
    (1100, "💥"),
)
_CALORIE_HEAVY_ICON = "🚨"


def _calorie_icon(calories: int) -> str:
    for threshold, icon in _CALORIE_TIERS:
        if calories < threshold:
            return icon
    return _CALORIE_HEAVY_ICON


_DAY_PROGRESS_TIERS = (
    (600, "🌅"),
    (1400, "🌤️"),
    (2200, "🌇"),
    (2800, "🌙"),
)
_DAY_PROGRESS_OVER_ICON = "⚠️"

# When the sender has a personal calorie target, day progress is shown as a
# coloured-circle fill gauge (a fraction of THAT target), not the time-of-day
# icons above, which read as morning/evening and get confused with the clock.
# Green while there is room, amber as it fills, red once the target is crossed.
_DAY_TARGET_TIERS = (
    (0.7, "🟢"),
    (0.95, "🟡"),
    (1.0, "🟠"),
)
_DAY_TARGET_OVER_ICON = "🔴"


def _today_line(daily_total: int, target: int | None) -> str:
    icon = _day_progress_icon(daily_total, target)
    if target and target > 0:
        if daily_total > target:
            return (
                f"{icon} Today's total: {daily_total} / {target} kcal "
                f"({daily_total - target} over)"
            )
        return f"{icon} Today's total: {daily_total} / {target} kcal"
    return f"{icon} Today's total: {daily_total} kcal"


def _day_progress_icon(daily_total: int, target: int | None = None) -> str:
    if target and target > 0:
        if daily_total > target:
            return _DAY_TARGET_OVER_ICON
        fraction = daily_total / target
        for threshold, icon in _DAY_TARGET_TIERS:
            if fraction <= threshold:
                return icon
        return _DAY_TARGET_OVER_ICON
    for threshold, icon in _DAY_PROGRESS_TIERS:
        if daily_total < threshold:
            return icon
    return _DAY_PROGRESS_OVER_ICON


_DISH_KEYWORDS = (
    (("salad", "greens", "lettuce", "spinach"), "🥗"),
    (("soup", "broth", "stew"), "🍲"),
    (("burger",), "🍔"),
    (("pizza",), "🍕"),
    (("pasta", "noodle", "ramen", "spaghetti"), "🍝"),
    (("sushi", "sashimi"), "🍣"),
    (("rice", "biryani", "pulao", "chawal"), "🍚"),
    (("dal", "curry", "sabzi", "sambar"), "🍛"),
    (("roti", "naan", "paratha", "chapati", "bread", "toast", "sandwich"), "🥪"),
    (("egg", "omelette", "omelet"), "🍳"),
    (("chicken", "fish", "meat", "lamb", "mutton", "beef", "pork", "kebab"), "🍗"),
    (("fruit", "apple", "banana", "mango", "berry", "orange"), "🍎"),
    (("cake", "cookie", "brownie", "dessert", "ice cream", "icecream", "chocolate", "sweet"), "🍰"),
    (("tea", "coffee", "chai", "latte"), "☕"),
    (("milk", "lassi", "smoothie", "shake", "juice"), "🥛"),
)
_DISH_DEFAULT_ICON = "🍽️"


def _dish_icon(dish: str) -> str:
    needle = dish.lower()
    for keywords, icon in _DISH_KEYWORDS:
        if any(word in needle for word in keywords):
            return icon
    return _DISH_DEFAULT_ICON
