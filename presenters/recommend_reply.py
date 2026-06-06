from html import escape

from domain.recommendation import MealRecommendationResult

RECOMMEND_REPLY_PARSE_MODE = "HTML"

# The bare-command prompt shown above the slot keyboard.
PICK_SLOT_TEXT = "What should I suggest? Pick a meal:"

# Telegram menu taps send /recommend with no arguments, so the slot is chosen
# via these buttons. The callback grammar is rec:<requester_id>:<slot>; the
# requester id is frozen into each button so only they can press it (R3).
_SLOT_ROWS = (("breakfast", "lunch"), ("dinner", "snack"))


def slot_keyboard(requester_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": slot.title(), "callback_data": f"rec:{requester_id}:{slot}"}
                for slot in row
            ]
            for row in _SLOT_ROWS
        ]
    }


def format_recommendation(
    result: MealRecommendationResult,
    *,
    for_label: str = "",
) -> str:
    """The recommendation as a Telegram HTML message. All LLM-originated text
    is escaped; empty optional fields are skipped, never rendered as None."""
    heading = "🍽 <b>What to eat next</b>"
    if for_label:
        heading += f" · {escape(for_label, quote=False)}"
    lines = [heading, f"<i>{escape(result.because_today, quote=False)}</i>", ""]
    for number, option in enumerate(result.options, start=1):
        lines.append(
            f"{number}. <b>{escape(option.title, quote=False)}</b>"
            f" · {escape(option.calorie_range, quote=False)}"
        )
        lines.append(f"   {escape(option.macro_shape, quote=False)}")
        lines.append(f"   {escape(option.why_it_fits, quote=False)}")
        if option.portion_tweak:
            lines.append(f"   ↳ {escape(option.portion_tweak, quote=False)}")
        lines.append("")
    lines.append("<i>Rough estimates, not medical advice.</i>")
    return "\n".join(lines)
