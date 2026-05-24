from collections.abc import Callable, Coroutine
from typing import Any

from openai import AsyncOpenAI

from core.settings import Settings
from domain.analysis import FoodAnalysis
from image_analyser.estimator import analyse_image

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
    ) -> FoodAnalysis:
        return await analyse_image(
            openai_client,
            model=model,
            image_bytes=image_bytes,
            media_type=media_type,
            caption=caption,
        )

    return estimator
