from dataclasses import dataclass

from openai import AsyncOpenAI

from core.settings import Settings
from domain.day import DayNote, Meal
from summary_analyser.summarizer import rerank_day_scores, write_day_note


@dataclass(frozen=True, slots=True)
class DaySummarizer:
    client: AsyncOpenAI
    model: str

    async def __call__(self, meals: list[Meal]) -> DayNote:
        return await write_day_note(self.client, model=self.model, meals=meals)

    async def rerank(
        self,
        users: list[tuple[str, list[Meal], DayNote]],
    ) -> dict[str, int]:
        return await rerank_day_scores(self.client, model=self.model, users=users)


def build_day_summarizer(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> DaySummarizer:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    return DaySummarizer(client=openai_client, model=settings.openai_model)
