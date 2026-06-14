"""Recipe video lookup via the official YouTube Data API.

One ``search.list`` call ordered by view count returns the most-watched recipe
videos for a dish; we pick one at random from the top ten so the same dish
doesn't keep surfacing the identical video on repeat calls (variety without a
second request). Never raises: any failure or missing key yields "" so the
recommendation still ships without a video.
"""

import logging
import random

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_TOP_N = 10  # pool the most-viewed results, then pick one for variety


async def recipe_video(dish: str, api_key: str | None) -> str:
    """A watch URL for ``dish``, chosen at random from the ``_TOP_N`` most-viewed
    recipe videos.

    View-count ordering favours well-established recipes; the random pick keeps
    the suggestion fresh across calls. Returns "" when there is no API key, no
    dish, or the lookup fails.
    """
    if not api_key or not dish.strip():
        return ""
    params = {
        "part": "snippet",
        "q": f"{dish} recipe",
        "type": "video",
        "maxResults": _TOP_N,
        "order": "viewCount",
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
        video_ids = [
            vid
            for item in items
            if (vid := item.get("id", {}).get("videoId"))
        ]
    except Exception:
        logger.exception("youtube recipe lookup failed dish=%s", dish)
        return ""
    if not video_ids:
        return ""
    return f"https://www.youtube.com/watch?v={random.choice(video_ids)}"
