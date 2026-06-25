"""Web search via the Tavily API.

One ``/search`` call returns an LLM-ready answer plus the top result snippets;
we fold them into a compact text block another prompt can read. Never raises:
any failure, missing key, or empty query yields "" so the caller's normal path
(its own nutrition knowledge, or a recommendation without inspiration) still
ships — same contract as the YouTube helper.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.tavily.com/search"


async def web_search(
    query: str, api_key: str | None, *, max_results: int = 3, timeout: float = 10.0
) -> str:
    """A compact snippet block for ``query``, or "" when unavailable.

    Uses Tavily's synthesized ``answer`` (when present) followed by the leading
    result contents, so the calling prompt gets grounded facts without raw HTML.
    ``timeout`` bounds the whole call so a slow Tavily never stalls a user reply.
    """
    if not api_key or not query.strip():
        return ""
    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": True,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                _SEARCH_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        # Never log the query: it can carry the user's free-form request text.
        logger.warning("tavily search failed: %s", type(error).__name__)
        return ""

    lines: list[str] = []
    answer = (data.get("answer") or "").strip()
    if answer:
        lines.append(answer)
    for result in data.get("results", []):
        content = (result.get("content") or "").strip()
        if content:
            lines.append(f"- {content}")
    return "\n".join(lines).strip()
