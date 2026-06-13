from openai import AsyncOpenAI


async def call_responses(
    client: AsyncOpenAI,
    *,
    model: str,
    system: str,
    user: str,
    image_data_url: str | None = None,
    image_detail: str = "high",
    tools: list[dict[str, object]] | None = None,
    response_format: dict[str, object] | None = None,
    cache_key: str | None = None,
    cache_retention: str | None = "24h",
) -> str:
    # OpenAI prompt caching is automatic for prompts >= 1024 tokens and works on an
    # exact-prefix match. Keep all static content (tools + the large system prompt)
    # at the front and every dynamic part (the user text and the image) last, so the
    # stable prefix is reused across requests. Do not interpolate per-request values
    # (caption, time, prior meals, the image) into `system` or `tools` or the cache
    # is busted on every call.
    user_content: list[dict[str, object]] = [{"type": "input_text", "text": user}]
    if image_data_url is not None:
        user_content.append(
            {
                "type": "input_image",
                "image_url": image_data_url,
                "detail": image_detail,
            }
        )

    kwargs: dict[str, object] = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {"role": "user", "content": user_content},
        ],
    }
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["text"] = {"format": response_format}
    # `prompt_cache_key` makes routing sticky so same-type requests land on the same
    # warm engine; `prompt_cache_retention="24h"` keeps the prefix cached for a day
    # instead of the default ~5-60 min in-memory window, which matters for a bot that
    # receives photos sporadically through the day.
    if cache_key:
        kwargs["prompt_cache_key"] = cache_key
    if cache_retention:
        kwargs["prompt_cache_retention"] = cache_retention

    response = await client.responses.create(**kwargs)
    return response.output_text
