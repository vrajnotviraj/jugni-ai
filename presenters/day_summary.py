from html import escape

from domain.day import DayReport, MealTimeline, UserDaySummary

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
        f"  ·  🔥 {user.calories} kcal  ·  {_score_emoji(user.health_score)} {user.health_score}/10"
    )

    meal_lines = [_format_meal_line(meal) for meal in user.meals_timeline]

    summary = (user.summary or "").strip()
    summary_block = (
        f"<blockquote>{escape(summary, quote=False)}</blockquote>" if summary else ""
    )

    parts = [header]
    if meal_lines:
        parts.append("\n".join(meal_lines))
    if summary_block:
        parts.append(summary_block)
    return "\n".join(parts)


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
