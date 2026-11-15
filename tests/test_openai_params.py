import asyncio
from types import SimpleNamespace

import pytest

from llm.openai_client import call_responses
from llm.smart_router import configure_router


class FakeClient:
    def __init__(self) -> None:
        self.kwargs: dict = {}
        self.responses = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(output_text="{}", usage=None)


def sent_kwargs(model: str) -> dict:
    configure_router(redis=None, flex_enabled=False, flex_timeout=1)
    client = FakeClient()
    asyncio.run(call_responses(client, model=model, system="s", user="u"))
    return client.kwargs


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-5.6-luna"])
def test_new_caching_api_models(model):
    kwargs = sent_kwargs(model)
    assert kwargs["extra_body"] == {"prompt_cache_options": {"ttl": "12h"}}
    assert "prompt_cache_retention" not in kwargs
    assert kwargs["reasoning"] == {"effort": "low"}


def test_older_reasoning_model_keeps_24h_retention():
    kwargs = sent_kwargs("gpt-5-mini")
    assert kwargs["prompt_cache_retention"] == "24h"
    assert "extra_body" not in kwargs
    assert kwargs["reasoning"] == {"effort": "low"}


@pytest.mark.parametrize("model", ["gpt-4.1-mini", "gpt-5-chat-latest"])
def test_non_reasoning_models_get_no_reasoning_param(model):
    kwargs = sent_kwargs(model)
    assert "reasoning" not in kwargs
    assert kwargs["prompt_cache_retention"] == "24h"
