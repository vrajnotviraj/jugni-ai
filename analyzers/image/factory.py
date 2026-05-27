from collections.abc import Callable, Coroutine
from typing import Any

from openai import AsyncOpenAI

from analyzers.image.estimator import analyse_image
from core.settings import Settings
from domain.analysis import FoodAnalysis

ImageEstimator = Callable[..., Coroutine[Any, Any, FoodAnalysis]]


def build_image_estimator(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> ImageEstimator:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    model = settings.openai_model

    async def estimator(
        image_bytes: bytes,
        media_type: str,
        caption: str | None = None,
        *,
        eaten_at: str | None = None,
        prior_meals: str | None = None,
    ) -> FoodAnalysis:
        return await analyse_image(
            openai_client,
            model=model,
            image_bytes=image_bytes,
            media_type=media_type,
            caption=caption,
            eaten_at=eaten_at,
            prior_meals=prior_meals,
        )

    return estimator
