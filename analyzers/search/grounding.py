"""When to reach for web search, and what to ask it.

The search is a tool the analyzers pull only when their own knowledge is thin:
an uncertain calorie estimate, or a recommendation that wants fresh ideas. Both
helpers return "" when there is no key or the lookup fails, so the analyzer's
normal path is untouched.
"""

from analyzers.search.tavily import web_search
from domain.analysis import MealExtraction

# Confidences that are worth a second, web-grounded look. A "high" extraction is
# already trusted, so it never spends a search call.
_UNSURE = frozenset({"low", "medium"})


async def nutrition_grounding(
    extraction: MealExtraction, api_key: str | None
) -> str:
    """Web snippets to re-ground an uncertain calorie estimate, or "".

    Returns "" when the estimate is already confident, the food is unidentified,
    there is no key, or the search fails — the caller then keeps its first pass.
    """
    if not api_key or not extraction.is_food or extraction.confidence not in _UNSURE:
        return ""
    query = f"{extraction.dish} calories and protein per serving nutrition facts"
    return await web_search(query, api_key)


def _diet_label(dietary: str | None) -> str:
    """A coarse veg/vegan tag for the search query, so durable health notes in
    the dietary facts (a condition, a medication from /context) are never sent to
    a third party. The recommend prompt still enforces the full dietary facts."""
    text = (dietary or "").casefold()
    if "vegan" in text:
        return "vegan"
    if ("veg" in text and "non veg" not in text.replace("-", " ")) or "jain" in text:
        return "vegetarian"
    return ""


async def recipe_inspiration(
    *, slot: str, user_request: str, dietary: str | None, api_key: str | None
) -> str:
    """Web snippets of creative meal ideas to widen the recommender, or "".

    Always searched when a key is present (a recommendation can always use a
    fresher idea); "" when there is no key or the lookup fails. Sends only a
    coarse diet tag plus the slot and the user's own request — never the raw
    dietary/profile facts. Bounded tightly so it cannot stall the reply.
    """
    if not api_key:
        return ""
    bits = ["creative wholesome", _diet_label(dietary), slot, "recipe ideas", user_request]
    query = " ".join(bit for bit in bits if bit.strip())
    return await web_search(query, api_key, timeout=6.0)
