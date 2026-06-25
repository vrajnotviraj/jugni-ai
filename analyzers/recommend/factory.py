from openai import AsyncOpenAI

from analyzers.recommend.recommender import Recommender
from core.settings import Settings


def build_recommender(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> Recommender:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    return Recommender(
        client=openai_client,
        model=settings.openai_model,
        youtube_api_key=settings.youtube_api_key,
        tavily_api_key=settings.tavily_api_key,
    )
