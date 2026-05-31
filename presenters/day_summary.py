import logging
from html import escape

from domain.day import DayMacros, DayReport, MealTimeline, UserDaySummary
from presenters.macros import macro_shares

logger = logging.getLogger(__name__)

NO_FOOD_PHOTOS_REPLY = "No food photos found for today."

SUMMARY_PARSE_MODE = "HTML"

_CHUNK_BUDGET = 4000
_SECTION_SEPARATOR = "\n\n"

_RANK_ICONS = {1: "🥇", 2: "🥈", 3: "🥉"}
_KEYCAP_NUMBERS = {
    4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟",
}


def format_day_summary(report: DayReport) -> str:
    if not report.users:
        return NO_FOOD_PHOTOS_REPLY

    sections = _build_sections(report)
    return _SECTION_SEPARATOR.join(sections)


def format_day_summary_chunks(report: DayReport) -> list[str]:
    if not report.users:
        return [NO_FOOD_PHOTOS_REPLY]

    sections = _build_sections(report)
    chunks: list[str] = []
    current = sections[0]
    for section in sections[1:]:
        candidate = current + _SECTION_SEPARATOR + section
        if len(candidate) <= _CHUNK_BUDGET:
            current = candidate
        else:
            chunks.append(current)
            current = section
    chunks.append(current)
    return chunks


def _build_sections(report: DayReport) -> list[str]:
    sections: list[str] = [f"🏆 <b>Healthiest eaters today</b> · {len(report.users)} 👥"]
    for user in report.users:
        sections.append(_format_user_block(user))
    return sections


def _format_user_block(user: UserDaySummary) -> str:
    header = (
        f"{_rank_icon(user.rank)} <b>{escape(user.sender_label, quote=False)}</b>"
        f"  ·  🍽️ {user.meal_periods_covered}/3"
        f"  ·  🔥 {user.calories} kcal"
        f"  ·  {_score_emoji(user.health_score)} {user.health_score}/10"
    )

    try:
        macro_line = _macro_line(user)
    except Exception:
        logger.exception("macro line rendering failed; omitting it from the summary")
        macro_line = None

    meal_lines = [_format_meal_line(meal) for meal in user.meals_timeline]

    summary = (user.summary or "").strip()
    summary_block = (
        f"<blockquote>{escape(summary, quote=False)}</blockquote>" if summary else ""
    )

    parts = [header]
    if macro_line:
        parts.append(macro_line)
    if meal_lines:
        parts.append("\n".join(meal_lines))
    if summary_block:
        parts.append(summary_block)
    return "\n".join(parts)


def _macro_line(user: UserDaySummary) -> str | None:
    """The day's protein/carb/fat balance as a share of calories, mirroring the
    photo reply. The macro that matters for this person's goal is bolded, and a
    single sugar/fibre flag is appended when the day is notably off on either.
    """
    ranked = macro_shares(
        user.macros.protein_g, user.macros.carb_g, user.macros.fat_g
    )
    if not ranked:
        return None
    pieces = []
    for label, icon, pct in ranked:
        text = f"{icon} {label} {pct}%"
        if label == user.highlight_macro:
            text = f"{icon} <b>{label} {pct}%</b>"
        pieces.append(text)
    line = " · ".join(pieces)
    flag = _macro_flag(user.macros, user.calories)
    if flag:
        line = f"{line}  ·  {flag}"
    return line


# A day clears these and the sugar/fibre flag fires. Added sugar at or above the
# FDA Daily Value (50 g) reads as high; fibre is flagged thin only once the day
# is substantial enough (>= 1200 kcal) that a real shortfall is meaningful, well
# under the ~25-30 g/day recommendation.
_HIGH_SUGAR_G = 50
_LOW_FIBRE_G = 15
_FIBRE_FLAG_MIN_KCAL = 1200


def _macro_flag(macros: DayMacros, calories: int) -> str | None:
    """At most one flag, worst-first: high added sugar, then thin fibre."""
    if macros.added_sugar_g >= _HIGH_SUGAR_G:
        return "🍬 high sugar"
    if calories >= _FIBRE_FLAG_MIN_KCAL and macros.fibre_g < _LOW_FIBRE_G:
        return "🌾 low fibre"
    return None


def _format_meal_line(meal: MealTimeline) -> str:
    time_label = meal.time or "--:--"
    dish = escape(meal.dish, quote=False)
    return f"• <code>{time_label}</code>  {dish} — {meal.calories} kcal"


def _rank_icon(rank: int) -> str:
    if rank in _RANK_ICONS:
        return _RANK_ICONS[rank]
    if rank in _KEYCAP_NUMBERS:
        return _KEYCAP_NUMBERS[rank]
    return f"#{rank}"


def _score_emoji(score: int) -> str:
    if score >= 8:
        return "💚"
    if score >= 5:
        return "💛"
    if score >= 3:
        return "🧡"
    return "❤️"
