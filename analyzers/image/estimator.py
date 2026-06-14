import base64
import logging
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

from analyzers.image.coaching import (
    FOOD_COACHING_RESPONSE_FORMAT,
    FOOD_COACHING_SYSTEM_PROMPT,
    fallback_coaching_tip,
    food_coaching_user_prompt,
    parse_coaching_tip,
)
from analyzers.image.extraction import (
    FOOD_EXTRACTION_RESPONSE_FORMAT,
    FOOD_EXTRACTION_SYSTEM_PROMPT,
    food_extraction_user_prompt,
    parse_meal_extraction,
)
from analyzers.image.preprocess import downscale_image
from domain.analysis import CoachingTip, FoodAnalysis, MealExtraction
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)

# Called with the extraction-only analysis (no tip yet) the moment the objective
# vision pass lands, before the slower coaching pass runs. The photo/intake
# workflows use it to persist the meal and flip it to "done" right away, so a
# repeat request sees a finished meal instead of waiting on the tip.
ExtractionHook = Callable[[FoodAnalysis], Awaitable[None]]


async def analyse_image(
    client: AsyncOpenAI,
    *,
    model: str,
    image_bytes: bytes,
    media_type: str,
    caption: str | None = None,
    sender_label: str | None = None,
    eaten_at: str | None = None,
    prior_meals: str | None = None,
    personal_context: str | None = None,
    personal_goal: str | None = None,
    protein_so_far_g: int | None = None,
    protein_target_g: int | None = None,
    on_extracted: ExtractionHook | None = None,
) -> FoodAnalysis:
    # Two passes: an objective vision extraction (numbers only, no goals or diet),
    # then a text-only coaching pass that reads those macros and the person's day
    # and decides what is worth saying. Splitting them keeps the calorie estimate
    # honest and lets each prompt stay small and cacheable.
    #
    # Cap the longest side so the patch-based vision model bills fewer image
    # tokens; this is the single boundary before OpenAI, so every caller (bot,
    # evals, API routes) benefits. Best-effort: it falls back to the original
    # bytes on any failure.
    image_bytes, media_type = downscale_image(image_bytes, media_type)
    raw_extraction = await call_responses(
        client,
        model=model,
        system=FOOD_EXTRACTION_SYSTEM_PROMPT,
        user=food_extraction_user_prompt(caption),
        image_data_url=_image_data_url(image_bytes, media_type),
        # `auto` lets the patch model size its own budget. We already cap the
        # longest side at 1024px in preprocess (the real cost control for a
        # patch-tokenised model), so forcing `high` only pins the maximum patch
        # count with no measured accuracy gain for portion/calorie estimation.
        image_detail="auto",
        response_format=FOOD_EXTRACTION_RESPONSE_FORMAT,
        cache_key="food-extraction",
    )
    extraction = parse_meal_extraction(raw_extraction)
    # Hand the objective result to the caller before the coaching pass: this is the
    # point the meal can be saved and marked "done" (the tip is best-effort and lands
    # later via set_tip).
    if on_extracted is not None:
        await on_extracted(merge_food_analysis(extraction))
    if not extraction.is_food:
        logger.info(
            "image extraction returned non-food confidence=%s",
            extraction.confidence,
        )
        return merge_food_analysis(extraction)

    # The coaching model reads the macros and the day and decides for itself what
    # is worth saying (a fun fact, honest praise, or one friendly tweak). We no
    # longer pre-pick an angle, so tips stop sounding templated.
    try:
        raw_coaching = await call_responses(
            client,
            model=model,
            system=FOOD_COACHING_SYSTEM_PROMPT,
            user=food_coaching_user_prompt(
                extraction,
                sender_label=sender_label,
                eaten_at=eaten_at,
                prior_meals=prior_meals,
                personal_context=personal_context,
                personal_goal=personal_goal,
                protein_so_far_g=protein_so_far_g,
                protein_target_g=protein_target_g,
            ),
            response_format=FOOD_COACHING_RESPONSE_FORMAT,
            cache_key="food-coaching",
        )
        coaching = parse_coaching_tip(raw_coaching)
        logger.info("image coaching fallback=false")
    except Exception as error:
        logger.warning("image coaching fallback: %s", error)
        coaching = fallback_coaching_tip()
    return merge_food_analysis(extraction, coaching)


def merge_food_analysis(
    extraction: MealExtraction,
    coaching: CoachingTip | None = None,
) -> FoodAnalysis:
    # Non-food (and the extraction-only path) carries no coaching, so the reply
    # simply shows no tip rather than a generic filler line.
    return FoodAnalysis(
        dish=extraction.dish,
        calories=extraction.calories,
        confidence=extraction.confidence,
        tip=coaching.tip if coaching else "",
        is_food=extraction.is_food,
        protein_g=extraction.protein_g,
        carb_g=extraction.carb_g,
        fat_g=extraction.fat_g,
        fibre_g=extraction.fibre_g,
        added_sugar_g=extraction.added_sugar_g,
        sat_fat_g=extraction.sat_fat_g,
        items=extraction.items,
    )


def _image_data_url(image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{media_type};base64,{encoded}"
