from html import escape

from domain.streak import AtRiskUser

STREAK_NUDGE_PARSE_MODE = "HTML"


def format_streak_nudge(at_risk: list[AtRiskUser]) -> str:
    """One consolidated group message naming everyone whose streak is at risk.

    Encouraging, never shaming: it asks people to log before the day ends, not
    "your streak is about to die".
    """
    header = "⏳ <b>Streak check</b> — log a meal before the day ends to keep it alive:"
    lines = [
        f"🔥 {escape(user.sender_label, quote=False)} · {user.streak} days"
        for user in at_risk
    ]
    return "\n".join([header, *lines])
