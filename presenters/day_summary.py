import logging
from html import escape

from domain.day import DayMacros, DayReport, MealTimeline, UserDaySummary
from presenters.macros import macro_shares, protein_progress

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


def format_day_summary_rich(report: DayReport) -> str | None:
    """The day summary as Bot API 10.1 rich HTML: a leaderboard table, then one
    collapsible section per person. None when nobody logged a meal."""
    if not report.users:
        return None
    rows = "".join(
        "<tr>"
        f'<td align="center">{_rank_icon(u.rank)}</td>'
        f"<td>{escape(u.sender_label, quote=False)}</td>"
        f'<td align="center">{_score_emoji(u.health_score)} {u.health_score}/10</td>'
        f'<td align="right">{u.calories}</td>'
        f'<td align="center">{u.meal_periods_covered}/3</td>'
        f'<td align="center">{f"🔥 {u.streak}d" if u.streak > 0 else "–"}</td>'
        "</tr>"
        for u in report.users
    )
    parts = [
        f"<h3>🏆 Healthiest eaters today · {len(report.users)} 👥</h3>",
        "<table bordered striped><tr><th>#</th><th>Who</th><th>Score</th>"
        f"<th>kcal</th><th>Meals</th><th>Streak</th></tr>{rows}</table>",
    ]
    for user in report.users:
        parts.append(_rich_user_details(user))
    return "".join(parts)


def _rich_user_details(user: UserDaySummary) -> str:
    body = []
    try:
        macro_line = _macro_line(user)
    except Exception:
        logger.exception("macro line rendering failed; omitting it from the summary")
        macro_line = None
    if macro_line:
        body.append(f"<p>{macro_line}</p>")
    if user.meals_timeline:
        meals = "".join(
            f"<li><code>{meal.time or '--:--'}</code> "
            f"{escape(meal.dish, quote=False)} — {meal.calories} kcal</li>"
            for meal in user.meals_timeline
        )
        body.append(f"<ul>{meals}</ul>")
    summary = (user.summary or "").strip()
    if summary:
        body.append(f"<blockquote>{escape(summary, quote=False)}</blockquote>")
    title = (
        f"{_rank_icon(user.rank)} {escape(user.sender_label, quote=False)}"
        f" · {user.calories} kcal"
    )
    return f"<details><summary>{title}</summary>{''.join(body)}</details>"


def _build_sections(report: DayReport) -> list[str]:
    sections: list[str] = [f"🏆 <b>Healthiest eaters today</b> · {len(report.users)} 👥"]
    for user in report.users:
        sections.append(_format_user_block(user))
    return sections


def _format_user_block(user: UserDaySummary) -> str:
    header = (
        f"{_rank_icon(user.rank)} <b>{escape(user.sender_label, quote=False)}</b>"
        f"  ·  🍽️ {user.meal_periods_covered}/3"
        f"  ·  ⚡ {user.calories} kcal"
        f"  ·  {_score_emoji(user.health_score)} {user.health_score}/10"
    )
    if user.streak > 0:
        header = f"{header}  ·  🔥 {user.streak}d"

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
    photo reply. The macro that matters for this person's goal is bolded, a
    protein-target gauge is appended when the person has a target (same
    coloured-circle design as the photo reply), and a single sugar/fibre flag
    is appended when the day is notably off on either.
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
    gauge = protein_progress(user.macros.protein_g, user.protein_target_g)
    if gauge:
        gauge_icon, gauge_pct = gauge
        line = f"{line}  ·  {gauge_icon} protein {gauge_pct}% of target"
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
