from domain.recommendation import MealRecommendationResult, RecommendedMealOption
from llm.json_parsing import parse_fenced_json

# Defensive caps so a runaway model can never flood a Telegram message.
_MAX_OPTIONS = 3
_TITLE_MAX = 80
_FIELD_MAX = 160
_REQUIRED_FIELDS = ("title", "calorie_range", "macro_shape", "why_it_fits")
_YOUTUBE_PREFIXES = (
    "https://www.youtube.com/",
    "https://youtube.com/",
    "https://youtu.be/",
)


def parse_recommendations(raw: str) -> MealRecommendationResult | None:
    """Validate the model's JSON into a result, or None for any malformed shape.

    None tells the recommender to fall back deterministically (R18); this
    function itself never raises.
    """
    try:
        payload = parse_fenced_json(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    because = payload.get("because_today")
    recipe_video_url = payload.get("recipe_video_url")
    raw_options = payload.get("options")
    if not isinstance(because, str) or not because.strip():
        return None
    if not isinstance(raw_options, list) or len(raw_options) < 2:
        return None

    options: list[RecommendedMealOption] = []
    for item in raw_options[:_MAX_OPTIONS]:
        if not isinstance(item, dict):
            return None
        fields: dict[str, str] = {}
        for key in _REQUIRED_FIELDS:
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                return None
            cap = _TITLE_MAX if key == "title" else _FIELD_MAX
            fields[key] = value.strip()[:cap]
        tweak = item.get("portion_tweak")
        options.append(
            RecommendedMealOption(
                **fields,
                portion_tweak=tweak.strip()[:_FIELD_MAX]
                if isinstance(tweak, str)
                else "",
            )
        )
    return MealRecommendationResult(
        because_today=because.strip()[:_FIELD_MAX],
        options=tuple(options),
        recipe_video_url=_clean_youtube_url(recipe_video_url),
    )


def _clean_youtube_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    url = value.strip()
    if any(url.startswith(prefix) for prefix in _YOUTUBE_PREFIXES):
        return url
    return ""
