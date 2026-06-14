import logging
from dataclasses import dataclass, replace

from openai import AsyncOpenAI

from analyzers.recommend.parser import parse_recommendations
from analyzers.recommend.prompts import (
    RECOMMEND_SYSTEM_PROMPT,
    recommend_user_prompt,
)
from analyzers.recommend.youtube import top_recipe_video
from domain.recommendation import (
    MealRecommendationContext,
    MealRecommendationResult,
    fallback_recommendation,
)
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Recommender:
    """Turns a precomputed context into meal options, then attaches a top
    recipe video for the first option. Never raises: any API or parse failure
    degrades to the deterministic rule-based fallback (R18)."""

    client: AsyncOpenAI
    model: str
    youtube_api_key: str | None = None

    async def __call__(
        self, context: MealRecommendationContext
    ) -> MealRecommendationResult:
        result = await self._suggest(context)
        url = await top_recipe_video(result.options[0].title, self.youtube_api_key)
        return replace(result, recipe_video_url=url)

    async def _suggest(
        self, context: MealRecommendationContext
    ) -> MealRecommendationResult:
        try:
            raw = await call_responses(
                self.client,
                model=self.model,
                system=RECOMMEND_SYSTEM_PROMPT,
                user=recommend_user_prompt(context),
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
