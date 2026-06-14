from html import escape

from domain.recommendation import MealRecommendationResult

RECOMMEND_REPLY_PARSE_MODE = "HTML"


def recommend_link_preview(result: MealRecommendationResult) -> dict:
    """The LinkPreviewOptions for the reply (Bot API). Every option carries its
    own recipe link, but Telegram only previews one URL — so show a small card
    for the first option that has a video, and disable the preview entirely when
    none do. The other options keep their inline Watch links without a card."""
    for option in result.options:
        if option.video_url:
            return {"url": option.video_url, "prefer_small_media": True}
    return {"is_disabled": True}


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
