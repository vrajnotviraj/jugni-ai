"""Top recipe video lookup via the official YouTube Data API.

One ``search.list`` call ranked by relevance (not raw view count, which
surfaces old generic videos over the actual dish) returns the single best
recipe video URL for a dish. Never raises: any failure or missing key yields
"" so the recommendation still ships without a video.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def top_recipe_video(dish: str, api_key: str | None) -> str:
    """The watch URL of the top relevance-ranked recipe video for ``dish``.

    Returns "" when there is no API key, no dish, or the lookup fails.
    """
    if not api_key or not dish.strip():
        return ""
    params = {
        "part": "snippet",
        "q": f"{dish} recipe",
        "type": "video",
        "maxResults": 1,
        "order": "relevance",
        "videoDuration": "medium",  # 4-20 min, the sweet spot for recipes
        "regionCode": "IN",
        "relevanceLanguage": "en",
        "key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_SEARCH_URL, params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
        video_id = items[0]["id"]["videoId"] if items else None
    except Exception:
        logger.exception("youtube recipe lookup failed dish=%s", dish)
        return ""
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
