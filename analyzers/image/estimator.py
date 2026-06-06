import base64

from openai import AsyncOpenAI

from analyzers.image.parser import parse_food_analysis
from analyzers.image.preprocess import downscale_image
from analyzers.image.prompts import (
    FOOD_ANALYSIS_SYSTEM_PROMPT,
    food_analysis_user_prompt,
)
from domain.analysis import FoodAnalysis
from llm.openai_client import call_responses


async def analyse_image(
    client: AsyncOpenAI,
    *,
    model: str,
    image_bytes: bytes,
    media_type: str,
    caption: str | None = None,
    eaten_at: str | None = None,
    prior_meals: str | None = None,
    personal_context: str | None = None,
    personal_goal: str | None = None,
    protein_so_far_g: int | None = None,
    protein_target_g: int | None = None,
) -> FoodAnalysis:
    # Cap the longest side so the patch-based vision model bills fewer image
    # tokens; this is the single boundary before OpenAI, so every caller (bot,
    # evals, API routes) benefits. Best-effort: it falls back to the original
    # bytes on any failure.
    image_bytes, media_type = downscale_image(image_bytes, media_type)
    raw = await call_responses(
        client,
        model=model,
        system=FOOD_ANALYSIS_SYSTEM_PROMPT,
        user=food_analysis_user_prompt(
            caption,
            eaten_at=eaten_at,
            prior_meals=prior_meals,
            personal_context=personal_context,
            personal_goal=personal_goal,
            protein_so_far_g=protein_so_far_g,
            protein_target_g=protein_target_g,
        ),
        image_data_url=_image_data_url(image_bytes, media_type),
        tools=[{"type": "web_search"}],
        cache_key="food-analysis",
    )
    return parse_food_analysis(raw)


def _image_data_url(image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{media_type};base64,{encoded}"
