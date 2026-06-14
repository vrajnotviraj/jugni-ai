from html import escape

from domain.recommendation import MealRecommendationResult

RECOMMEND_REPLY_PARSE_MODE = "HTML"

# Every option now carries its own recipe link, so a single preview card can't
# represent the list — Telegram only ever previews one URL. Suppress the preview
# and keep the watch links inline (Bot API LinkPreviewOptions).
RECOMMEND_LINK_PREVIEW = {"is_disabled": True}


def format_recommendation(
    result: MealRecommendationResult,
    *,
    for_label: str = "",
) -> str:
    """The recommendation as a Telegram HTML message. All LLM-originated text
    is escaped. Each option is a tight block so the list scans fast: a bold
    title, a monospace calorie tag with the italic reason, and its own recipe
    link. The day's read sits in a blockquote up top."""
    heading = "🍽 <b>What to eat next</b>"
    if for_label:
        heading += f" · {escape(for_label, quote=False)}"
    lines = [
        heading,
        f"<blockquote>{escape(result.because_today, quote=False)}</blockquote>",
    ]
    for number, option in enumerate(result.options, start=1):
        lines.append("")
        lines.append(f"<b>{number} · {escape(option.title, quote=False)}</b>")
        lines.append(
            f"<code>{escape(option.calorie_range, quote=False)}</code>  "
            f"<i>{escape(option.why, quote=False)}</i>"
        )
        if option.video_url:
            lines.append(
                f'▶ <a href="{escape(option.video_url)}">Watch the recipe</a>'
            )
    return "\n".join(lines)
