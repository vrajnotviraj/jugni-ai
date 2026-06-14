from collections.abc import Callable, Coroutine
from typing import Any

from openai import AsyncOpenAI

from analyzers.image.estimator import ExtractionHook
from analyzers.intake.analyzer import analyse_intake
from core.settings import Settings
from domain.analysis import FoodAnalysis

IntakeAnalyzer = Callable[..., Coroutine[Any, Any, FoodAnalysis]]


def build_intake_analyzer(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> IntakeAnalyzer:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    model = settings.openai_model

    async def analyzer(
        text: str,
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
        return await analyse_intake(
            openai_client,
            model=model,
            text=text,
            sender_label=sender_label,
            eaten_at=eaten_at,
            prior_meals=prior_meals,
            personal_context=personal_context,
            personal_goal=personal_goal,
            protein_so_far_g=protein_so_far_g,
            protein_target_g=protein_target_g,
            on_extracted=on_extracted,
        )

    return analyzer
