import base64

from openai import AsyncOpenAI

from ai.openai_client import call_responses
from domain.analysis import FoodAnalysis
from image_analyser.parser import parse_food_analysis
from image_analyser.prompts import (
    FOOD_ANALYSIS_SYSTEM_PROMPT,
    food_analysis_user_prompt,
)


async def analyse_image(
    client: AsyncOpenAI,
    *,
    model: str,
    image_bytes: bytes,
    media_type: str,
    caption: str | None = None,
) -> FoodAnalysis:
    raw = await call_responses(
        client,
        model=model,
        system=FOOD_ANALYSIS_SYSTEM_PROMPT,
        user=food_analysis_user_prompt(caption),
        image_data_url=_image_data_url(image_bytes, media_type),
    )
    return parse_food_analysis(raw)


def _image_data_url(image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{media_type};base64,{encoded}"
