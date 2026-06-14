import asyncio
import logging
from dataclasses import dataclass, replace

from openai import AsyncOpenAI

from analyzers.recommend.parser import parse_recommendations
from analyzers.recommend.prompts import (
    RECOMMEND_SYSTEM_PROMPT,
    recommend_user_prompt,
)
from analyzers.recommend.youtube import recipe_video
from domain.recommendation import (
    MealRecommendationContext,
    MealRecommendationResult,
    RecommendedMealOption,
    fallback_recommendation,
)
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Recommender:
    """Turns a precomputed context into meal options, then attaches a recipe
    video to each one (fetched concurrently). Never raises: any API or parse
    failure degrades to the deterministic rule-based fallback (R18), and a
    missing video just leaves that option without a link."""

    client: AsyncOpenAI
    model: str
    youtube_api_key: str | None = None

    async def __call__(
        self, context: MealRecommendationContext
    ) -> MealRecommendationResult:
        result = await self._suggest(context)
        options = await asyncio.gather(
            *(self._with_video(option) for option in result.options)
        )
        return replace(result, options=tuple(options))

    async def _with_video(
        self, option: RecommendedMealOption
    ) -> RecommendedMealOption:
        url = await recipe_video(option.title, self.youtube_api_key)
        return replace(option, video_url=url)

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
