from dataclasses import dataclass

from openai import AsyncOpenAI

from analyzers.summary.summarizer import write_day_note
from core.settings import Settings
from domain.day import DayNote, Meal


@dataclass(frozen=True, slots=True)
class DaySummarizer:
    client: AsyncOpenAI
    model: str

    async def __call__(self, meals: list[Meal], *, as_of: str = "") -> DayNote:
        return await write_day_note(
            self.client, model=self.model, meals=meals, as_of=as_of
        )


def build_day_summarizer(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> DaySummarizer:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    return DaySummarizer(client=openai_client, model=settings.openai_model)
