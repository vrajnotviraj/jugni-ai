import logging

from openai import AsyncOpenAI

from analyzers.image.coaching import (
    FOOD_COACHING_RESPONSE_FORMAT,
    FOOD_COACHING_SYSTEM_PROMPT,
    fallback_coaching_tip,
    food_coaching_user_prompt,
    parse_coaching_tip,
)
from analyzers.image.estimator import ExtractionHook, merge_food_analysis
from analyzers.image.extraction import (
    FOOD_EXTRACTION_RESPONSE_FORMAT,
    parse_meal_extraction,
)
from analyzers.intake.prompts import (
    INTAKE_EXTRACTION_SYSTEM_PROMPT,
    intake_extraction_user_prompt,
)
from analyzers.search.grounding import nutrition_grounding
from domain.analysis import FoodAnalysis
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)


async def analyse_intake(
    client: AsyncOpenAI,
    *,
    model: str,
    text: str,
    sender_label: str | None = None,
    eaten_at: str | None = None,
    prior_meals: str | None = None,
    personal_context: str | None = None,
    personal_goal: str | None = None,
    protein_so_far_g: int | None = None,
    protein_target_g: int | None = None,
    tavily_api_key: str | None = None,
    on_extracted: ExtractionHook | None = None,
) -> FoodAnalysis:
    # Same two passes as the photo path: an objective text extraction (numbers
    # only, grounded in the model's own nutrition knowledge), then the shared
    # text-only coaching pass. Reusing the photo schema, parser, and coaching
    # keeps a typed meal's output identical in shape to a photographed one.
    raw_extraction = await call_responses(
        client,
        model=model,
        system=INTAKE_EXTRACTION_SYSTEM_PROMPT,
        user=intake_extraction_user_prompt(text),
        response_format=FOOD_EXTRACTION_RESPONSE_FORMAT,
        cache_key="intake-extraction",
    )
    extraction = parse_meal_extraction(raw_extraction)
    # When that first pass is unsure, web-search the dish and re-extract with the
    # fresh facts in hand (the on-demand "tool call"). Best-effort: no key, no
    # snippets, or a re-parse failure all keep the first estimate.
    snippets = await nutrition_grounding(extraction, tavily_api_key)
    if snippets:
        logger.info("intake grounding via web search dish=%s", extraction.dish)
        # Best-effort: a failed or unparseable grounding pass keeps the first
        # estimate — search never breaks the normal path.
        try:
            raw_grounded = await call_responses(
                client,
                model=model,
                system=INTAKE_EXTRACTION_SYSTEM_PROMPT,
                user=intake_extraction_user_prompt(text, web_context=snippets),
                response_format=FOOD_EXTRACTION_RESPONSE_FORMAT,
                cache_key="intake-extraction",
            )
            extraction = parse_meal_extraction(raw_grounded)
        except Exception as error:
            logger.warning("intake grounding re-extraction failed: %s", error)
    # Hand the objective result to the caller before coaching; for a typed meal the
    # caller persists it only when it's loggable (food + confident enough), so the
    # rejected branches below still store nothing.
    if on_extracted is not None:
        await on_extracted(merge_food_analysis(extraction))
    if not extraction.is_food:
        logger.info(
            "intake extraction returned non-food confidence=%s", extraction.confidence
        )
        return merge_food_analysis(extraction)

    # A low-confidence text intake is rejected upstream (handle_intake), so skip
    # the coaching call for it: there is no card to attach a tip to.
    if extraction.confidence == "low":
        logger.info("intake extraction low-confidence; skipping coaching")
        return merge_food_analysis(extraction)

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
        logger.info("intake coaching fallback=false")
    except Exception as error:
        logger.warning("intake coaching fallback: %s", error)
        coaching = fallback_coaching_tip()
    return merge_food_analysis(extraction, coaching)
