from collections.abc import Callable, Coroutine
from typing import Any

from openai import AsyncOpenAI

from analyzers.image.estimator import ExtractionHook, analyse_image
from core.settings import Settings
from domain.analysis import FoodAnalysis

ImageEstimator = Callable[..., Coroutine[Any, Any, FoodAnalysis]]


def build_image_estimator(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> ImageEstimator:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    model = settings.openai_model
    tavily_api_key = settings.tavily_api_key

    async def estimator(
        image_bytes: bytes,
        media_type: str,
        caption: str | None = None,
        *,
        sender_label: str | None = None,
        eaten_at: str | None = None,
        prior_meals: str | None = None,
        personal_context: str | None = None,
        personal_goal: str | None = None,
        protein_so_far_g: int | None = None,
        protein_target_g: int | None = None,
        on_extracted: ExtractionHook | None = None,
    ) -> FoodAnalysis:
        return await analyse_image(
            openai_client,
            model=model,
            image_bytes=image_bytes,
            media_type=media_type,
            caption=caption,
            sender_label=sender_label,
            eaten_at=eaten_at,
            prior_meals=prior_meals,
            personal_context=personal_context,
            personal_goal=personal_goal,
            protein_so_far_g=protein_so_far_g,
            protein_target_g=protein_target_g,
            tavily_api_key=tavily_api_key,
            on_extracted=on_extracted,
        )

    return estimator
