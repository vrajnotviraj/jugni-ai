import json
import logging
import random
from html import escape
from pathlib import Path

from domain.analysis import FoodAnalysis
from domain.streak import StreakState
from presenters.macros import macro_shares, protein_progress

logger = logging.getLogger(__name__)

NOT_FOOD_REPLY = "Doesn't look like food. Send a food photo to get a calorie estimate."

_CONFIDENCE_ICONS = {"medium": "⚖️", "low": "❓"}

MEAL_WIDGET = (
    Path(__file__).resolve().parent.parent / "assets" / "widgets" / "meal.html"
).read_text()
# Bot API 10.4 caps a widget's chat_data at 1024 bytes.
_WIDGET_DATA_LIMIT = 1024


def format_photo_reply(
    sender_label: str,
    analysis: FoodAnalysis,
    daily_total: int,
    streak_line: str | None = None,
    eaten_at: str | None = None,
    calorie_target: int | None = None,
    protein_today_g: int | None = None,
    protein_target_g: int | None = None,
) -> str:
    if not analysis.is_food:
        return NOT_FOOD_REPLY

    header = (
        f"{_dish_icon(analysis.dish)} <b>{escape(sender_label, quote=False)}'s meal</b>"
    )
    dish_line = f"Dish: {escape(analysis.dish, quote=False)}"
    calories_line = (
        f"{_calorie_icon(analysis.calories)} Calories: {analysis.calories} kcal"
    )
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
    protein_line = _protein_progress_line(protein_today_g, protein_target_g)
    if protein_line:
        nutrition.append(protein_line)
    nutrition.append(confidence_line)

    # The whole reply is one message: identity, the numbers, the collapsible
    # breakdown that explains the calorie total, an optional tip, then the
    # streak shout-out. Each is its own blank-line-separated group.
    groups = [identity, nutrition]
    breakdown = _breakdown_block(analysis.items)
    if breakdown:
        groups.append([breakdown])
    tip = _tip_block(analysis.tip)
    if tip:
        groups.append([tip])
    if streak_line:
        groups.append([streak_line])

    return "\n\n".join("\n".join(group) for group in groups)


def format_photo_replies(
    sender_label: str,
    analysis: FoodAnalysis,
    daily_total: int,
    *,
    streak_line: str | None,
    eaten_at: str | None,
    calorie_target: int | None,
    protein_today_g: int | None,
    protein_target_g: int | None,
) -> tuple[str, str | None, tuple[str, str] | None]:
    """(classic HTML card, rich HTML card or None, (widget html, chat_data) or
    None) for the same meal."""
    args = (sender_label, analysis, daily_total)
    kwargs = dict(
        streak_line=streak_line,
        eaten_at=eaten_at,
        calorie_target=calorie_target,
        protein_today_g=protein_today_g,
        protein_target_g=protein_target_g,
    )
    data = format_photo_widget_data(*args, **kwargs)
    return (
        format_photo_reply(*args, **kwargs),
        format_photo_reply_rich(*args, **kwargs),
        (MEAL_WIDGET, data) if data is not None else None,
    )


def format_photo_widget_data(
    sender_label: str,
    analysis: FoodAnalysis,
    daily_total: int,
    streak_line: str | None = None,
    eaten_at: str | None = None,
    calorie_target: int | None = None,
    protein_today_g: int | None = None,
    protein_target_g: int | None = None,
) -> str | None:
    """The meal card's state as compact JSON for ``assets/widgets/meal.html``.
    The widget renders it with textContent, so nothing here needs escaping.
    Items, then the tip, are trimmed until it fits the 1024-byte cap."""
    if not analysis.is_food:
        return None
    data = {
        "who": sender_label,
        "at": eaten_at,
        "conf": analysis.confidence,
        "dish": analysis.dish,
        "kcal": analysis.calories,
        "p": analysis.protein_g,
        "c": analysis.carb_g,
        "f": analysis.fat_g,
        "day": daily_total,
        "goal": calorie_target,
        "pd": protein_today_g,
        "pg": protein_target_g,
        "items": [item for item in analysis.items if item.strip()],
        "tip": (analysis.tip or "").strip(),
        "streak": streak_line,
    }

    def encode() -> str:
        compact = {k: v for k, v in data.items() if v not in (None, "", [])}
        return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))

    payload = encode()
    while len(payload.encode()) > _WIDGET_DATA_LIMIT and data["items"]:
        data["items"].pop()
        payload = encode()
    while len(payload.encode()) > _WIDGET_DATA_LIMIT and data["tip"]:
        data["tip"] = data["tip"][: max(0, len(data["tip"]) - 40)].rstrip() + "…"
        if len(data["tip"]) <= 1:
            data["tip"] = ""
        payload = encode()
    # Dish, names and streak are short; if they still overflow, skip the widget.
    return payload if len(payload.encode()) <= _WIDGET_DATA_LIMIT else None


def format_photo_reply_rich(
    sender_label: str,
    analysis: FoodAnalysis,
    daily_total: int,
    streak_line: str | None = None,
    eaten_at: str | None = None,
    calorie_target: int | None = None,
    protein_today_g: int | None = None,
    protein_target_g: int | None = None,
) -> str | None:
    """The same card as :func:`format_photo_reply`, as Bot API 10.1 rich HTML:
    a heading, a macro table, progress bars, and a collapsible breakdown.
    None for non-food (the plain one-liner is sent instead)."""
    if not analysis.is_food:
        return None

    def esc(text: str) -> str:
        return escape(text, quote=False)

    meta = [f"<b>{esc(analysis.dish)}</b>"]
    if eaten_at:
        meta.append(f"🕐 {esc(eaten_at)}")
    meta.append(f"{_confidence_line(analysis.confidence)}")
    parts = [
        f"<h3>{_dish_icon(analysis.dish)} {esc(sender_label)}'s meal</h3>",
        f"<p>{' · '.join(meta)}</p>",
        _macro_table(analysis),
    ]

    progress = [
        f"{_day_progress_icon(daily_total, calorie_target)} <b>Today</b> "
        f"{daily_total} kcal{_bar(daily_total, calorie_target)}"
    ]
    gauge = protein_progress(protein_today_g or 0, protein_target_g)
    if gauge:
        progress.append(
            f"{gauge[0]} <b>Protein</b> {protein_today_g}g"
            f"{_bar(protein_today_g or 0, protein_target_g)}"
        )
    parts.extend(f"<p>{line}</p>" for line in progress)

    items = [item for item in analysis.items if item.strip()]
    if items:
        rows = "".join(f"<li>{esc(item)}</li>" for item in items)
        parts.append(
            f"<details><summary>What's in it</summary><ul>{rows}</ul></details>"
        )
    tip = (analysis.tip or "").strip()
    if tip:
        parts.append(f"<blockquote>💡 <b>Tip</b><br>{esc(tip)}</blockquote>")
    if streak_line:
        parts.append(f"<p>{esc(streak_line)}</p>")
    return "".join(parts)


def _macro_table(analysis: FoodAnalysis) -> str:
    """Calories plus each macro's grams and share of calories, one column each."""
    shares = {
        label: pct
        for label, _, pct in macro_shares(
            analysis.protein_g, analysis.carb_g, analysis.fat_g
        )
        or []
    }
    head = [f"{_calorie_icon(analysis.calories)} kcal"]
    body = [str(analysis.calories)]
    for label, icon, grams in (
        ("Protein", "💪", analysis.protein_g),
        ("Carbs", "🍚", analysis.carb_g),
        ("Fat", "🧈", analysis.fat_g),
    ):
        head.append(f"{icon} {label}")
        pct = f" · {shares[label]}%" if label in shares else ""
        body.append(f"{grams}g{pct}")
    th = "".join(f"<th>{h}</th>" for h in head)
    td = "".join(f'<td align="center">{b}</td>' for b in body)
    return f"<table bordered striped><tr>{th}</tr><tr>{td}</tr></table>"


def _bar(value: int, target: int | None, width: int = 10) -> str:
    """`` ▰▰▰▱▱ 62%`` against a target, or empty when there is no target."""
    if not target or target <= 0:
        return ""
    fraction = value / target
    filled = min(width, round(fraction * width))
    return f"  {'▰' * filled}{'▱' * (width - filled)} {round(fraction * 100)}%"


def _tip_block(tip: str) -> str | None:
    tip = (tip or "").strip()
    if not tip:
        return None
    return f"💡 <b>Tip</b>\n{escape(tip, quote=False)}"


def _breakdown_block(items: tuple[str, ...]) -> str | None:
    """The per-item calorie breakdown as a collapsible quote, so the total is
    transparent without crowding the card. Telegram shows the first line and
    expands the rest on tap."""
    items = tuple(item for item in items if item.strip())
    if not items:
        return None
    lines = "\n".join(f"• {escape(item, quote=False)}" for item in items)
    return f"<blockquote expandable>What's in it\n{lines}</blockquote>"


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


def _protein_progress_line(today_g: int | None, target_g: int | None) -> str | None:
    """How much of the day's protein target is met, e.g. "🟠 Protein today:
    58g (48%)". Mirrors the calorie line's design: the coloured-circle gauge
    encodes progress against the personal target and the explicit "/ target g"
    figure is dropped to keep the reply uncluttered.
    """
    gauge = protein_progress(today_g or 0, target_g)
    if not gauge:
        return None
    icon, pct = gauge
    return f"{icon} Protein today: {today_g}g ({pct}%)"


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
    # The icon already encodes progress toward the personal target (a coloured-circle
    # fill gauge), so the line itself only carries the running total — the explicit
    # "/ target kcal" figure is dropped to keep the reply uncluttered.
    icon = _day_progress_icon(daily_total, target)
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
    (
        (
            "cake",
            "cookie",
            "brownie",
            "dessert",
            "ice cream",
            "icecream",
            "chocolate",
            "sweet",
        ),
        "🍰",
    ),
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
