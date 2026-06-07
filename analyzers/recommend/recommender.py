import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from analyzers.recommend.parser import parse_recommendations
from analyzers.recommend.prompts import (
    RECOMMEND_SYSTEM_PROMPT,
    recommend_user_prompt,
)
from domain.recommendation import (
    MealRecommendationContext,
    MealRecommendationResult,
    fallback_recommendation,
)
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)

_YOUTUBE_SEARCH_TOOL = {
    "type": "web_search",
    "search_context_size": "low",
}


@dataclass(frozen=True, slots=True)
class Recommender:
    """Turns a precomputed context into meal options. Never raises: any API or
    parse failure degrades to the deterministic rule-based fallback (R18)."""

    client: AsyncOpenAI
    model: str

    async def __call__(
        self, context: MealRecommendationContext
    ) -> MealRecommendationResult:
        try:
            raw = await call_responses(
                self.client,
                model=self.model,
                system=RECOMMEND_SYSTEM_PROMPT,
                user=recommend_user_prompt(context),
                tools=[_YOUTUBE_SEARCH_TOOL],
                cache_key="recommend",
            )
            result = parse_recommendations(raw)
        except Exception:
            logger.exception("recommendation call failed; using fallback")
            return fallback_recommendation(context)
        if result is None:
            logger.info("recommendation output unparseable; using fallback")
            return fallback_recommendation(context)
        return result
