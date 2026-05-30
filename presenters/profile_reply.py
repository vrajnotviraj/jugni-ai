from datetime import datetime
from html import escape

from domain.profile import ProfileExtraction, UserProfile

PROFILE_REPLY_PARSE_MODE = "HTML"

_NOT_SET = "not set"

# Human-readable labels for the fields the extractor can reject, so a confirmation
# can name exactly what did not land.
_IGNORED_LABELS = {
    "height": "height",
    "weight": "weight",
    "timezone": "timezone",
}


def format_profile(profile: UserProfile, *, now: datetime) -> str:
    name = profile.display_name or "Your"
    lines = [
        f"👤 <b>{escape(_possessive(name), quote=False)} profile</b>",
        f"Height: {_height(profile.height_cm)}",
        f"Weight: {_weight(profile, now=now)}",
        f"Age: {_opt(profile.age)}",
        f"Sex: {_opt(profile.sex)}",
        f"Activity: {_opt(profile.activity)}",
        f"Goal: {_value(profile.goal)}",
        f"Diet: {_value(profile.diet)}",
        f"Timezone: {_value(profile.timezone)}",
    ]
    return "\n".join(lines)


def format_profile_saved(
    extraction: ProfileExtraction,
    nudge: str | None,
) -> str:
    lines = ["✅ <b>Got it, saved.</b>"]
    lines.extend(_understood_lines(extraction))

    ignored = [
        _IGNORED_LABELS[name]
        for name in extraction.ignored
        if name in _IGNORED_LABELS
    ]
    if ignored:
        lines.append(
            "I could not use your "
            + _join(ignored)
            + " (it looked off), so I left it as is."
        )

    if nudge:
        lines.append("")
        lines.append(nudge)
    return "\n".join(lines)


def format_profile_not_understood() -> str:
    return (
        "I could not pull any profile details from that. Tell me in plain words, "
        "for example: <code>/profile 5ft9, 72 kg, vegetarian, want to lose fat</code>."
    )


def format_profile_new_user(display_name: str) -> str:
    name = display_name or "there"
    return "\n".join(
        [
            f"👋 Hi {escape(name, quote=False)}, you do not have a profile yet.",
            "Set it in plain words, for example:",
            "<code>/profile 5ft9, 72 kg, vegetarian, want to lose fat</code>",
            "Then I will tailor your photo estimates to you.",
        ]
    )


def format_context_list(notes: list[str]) -> str:
    if not notes:
        return (
            "You have no context notes yet. Add one and I will respect it in "
            "every future estimate, for example: "
            "<code>/addcontext my chundo has no sugar</code>."
        )
    lines = ["📝 <b>Your context notes</b>"]
    lines.extend(f"• {escape(note, quote=False)}" for note in notes)
    return "\n".join(lines)


def format_context_saved(notes: list[str], nudge: str | None) -> str:
    # The notes are AI-consolidated on every add, so show the full current set
    # rather than just the line the user typed.
    count = len(notes)
    plural = "note" if count == 1 else "notes"
    lines = [
        "✅ <b>Context saved.</b>",
        f"I tidied things up. You now have {count} {plural} I will factor into "
        "your estimates:",
    ]
    lines.extend(f"• {escape(note, quote=False)}" for note in notes)
    if nudge:
        lines.append("")
        lines.append(nudge)
    return "\n".join(lines)


def format_profile_deleted() -> str:
    return (
        "🗑️ Your profile, context notes, and weight history are deleted. "
        "Send <code>/profile</code> any time to start fresh."
    )


def format_help(display_name: str) -> str:
    name = display_name or "there"
    return "\n".join(
        [
            f"👋 Hi {escape(name, quote=False)}, here is what I can do in this chat:",
            "",
            "<b>/profile</b> — view your profile, or set it in plain words.",
            "  e.g. <code>/profile 5ft9, 72 kg, vegetarian, lose fat</code>",
            "<b>/addcontext</b> — add a standing note I respect in estimates.",
            "  e.g. <code>/addcontext my chundo has no sugar</code>",
            "<b>/seecontext</b> — see your saved context notes.",
            "<b>/deleteprofile</b> — delete everything I store about you.",
            "",
            "Your profile is private to this chat and never shown in any group.",
        ]
    )


def _understood_lines(extraction: ProfileExtraction) -> list[str]:
    lines: list[str] = []
    if extraction.height_cm is not None:
        lines.append(f"Height: {extraction.height_cm} cm")
    if extraction.weight_kg is not None:
        lines.append(f"Weight: {_fmt_weight(extraction.weight_kg)} kg")
    if extraction.age is not None:
        lines.append(f"Age: {extraction.age}")
    if extraction.sex is not None:
        lines.append(f"Sex: {escape(extraction.sex, quote=False)}")
    if extraction.activity is not None:
        lines.append(f"Activity: {escape(extraction.activity, quote=False)}")
    if extraction.goal is not None:
        lines.append(f"Goal: {escape(extraction.goal, quote=False)}")
    if extraction.diet is not None:
        lines.append(f"Diet: {escape(extraction.diet, quote=False)}")
    if extraction.timezone is not None:
        lines.append(f"Timezone: {escape(extraction.timezone, quote=False)}")
    return lines


def _height(height_cm: int | None) -> str:
    return f"{height_cm} cm" if height_cm is not None else _NOT_SET


def _weight(profile: UserProfile, *, now: datetime) -> str:
    if profile.weight_kg is None:
        return _NOT_SET
    base = f"{_fmt_weight(profile.weight_kg)} kg"
    days = profile.days_since_weight_update(now)
    if days is None:
        return base
    return f"{base} ({_age_phrase(days)})"


def _age_phrase(days: int) -> str:
    if days <= 0:
        return "updated today"
    if days == 1:
        return "updated yesterday"
    return f"updated {days} days ago"


def _value(value: str | None) -> str:
    if not value:
        return _NOT_SET
    return escape(value, quote=False)


def _opt(value: object) -> str:
    if value is None or value == "":
        return _NOT_SET
    return escape(str(value), quote=False)


def _fmt_weight(weight_kg: float) -> str:
    if weight_kg == int(weight_kg):
        return str(int(weight_kg))
    return f"{weight_kg:g}"


def _possessive(name: str) -> str:
    if name == "Your":
        return name
    return f"{name}'s"


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
