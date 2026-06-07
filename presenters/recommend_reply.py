from html import escape

from domain.recommendation import MealRecommendationResult

RECOMMEND_REPLY_PARSE_MODE = "HTML"

# The bare-command prompt shown above the slot keyboard.
PICK_SLOT_TEXT = "What should I suggest? Pick a meal:"

# Telegram reply keyboard buttons send their text as normal user messages, so
# this stays on the ordinary /recommend command path with no callback handling.
_SLOT_ROWS = (("breakfast", "lunch"), ("dinner", "snack"))

SLOT_KEYBOARD = {
    "keyboard": [[f"/recommend {slot}" for slot in row] for row in _SLOT_ROWS],
    "one_time_keyboard": True,
    "resize_keyboard": True,
}


def format_recommendation(
    result: MealRecommendationResult,
    *,
    for_label: str = "",
) -> str:
    """The recommendation as a Telegram HTML message. All LLM-originated text
    is escaped. Each option is a tight two-line block so the list scans fast."""
    heading = "🍽 <b>What to eat next</b>"
    if for_label:
        heading += f" · {escape(for_label, quote=False)}"
    lines = [heading, f"<i>{escape(result.because_today, quote=False)}</i>"]
    for number, option in enumerate(result.options, start=1):
        lines.append("")
        lines.append(f"<b>{number}. {escape(option.title, quote=False)}</b>")
        lines.append(
            f"{escape(option.calorie_range, quote=False)} · "
            f"<i>{escape(option.why, quote=False)}</i>"
        )
    if result.recipe_video_url:
        lines.append("")
        lines.append(
            f'▶ <a href="{escape(result.recipe_video_url)}">Top recipe video</a>'
        )
    lines.append("")
    lines.append("<i>Rough estimates, not medical advice.</i>")
    return "\n".join(lines)
