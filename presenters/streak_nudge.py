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
    last = [escape(u.sender_label, quote=False) for u in at_risk if u.last_reminder]
    if last:
        lines.append(
            f"\n🔕 That's the last reminder for {', '.join(last)} for now. "
            "I'll stay quiet so it doesn't get noisy. Keep going!"
        )
    return "\n".join([header, *lines])
