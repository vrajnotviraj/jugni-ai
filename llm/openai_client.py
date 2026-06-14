import logging

from openai import APIStatusError, APITimeoutError, AsyncOpenAI

from llm.smart_router import pick_route, report_unavailable

logger = logging.getLogger(__name__)


def _flex_unavailable(exc: APITimeoutError | APIStatusError) -> bool:
    """True when an error means "flex can't serve this" — so mark flex down.

    Covers the three ways flex bows out: it timed out, it's out of capacity (429),
    or the model doesn't offer flex at all (400 naming service_tier — a backstop;
    the model allowlist already keeps unsupported models off flex). Any other
    status is a real error and must surface unchanged.
    """
    if isinstance(exc, APITimeoutError):
        return True
    if exc.status_code == 429:
        return True
    return exc.status_code == 400 and "service_tier" in str(exc).lower()


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

    # The smart router picks the route: the flex tier when this model supports it
    # and flex is healthy, else the primary tier. A flex route carries a longer
    # timeout (slow is fine on the cheap lane). When flex bows out (it ran past the
    # flex timeout, or hit a 429), we mark it down for 30 minutes AND fall through to
    # the primary tier in this same call, so the request still succeeds — at the cost
    # of stacking the primary call after flex's timeout this once. The breaker means
    # only the first call in a 30-minute window pays that stacked latency; every
    # later call routes straight to primary. Any other error from the flex attempt is
    # a real failure and surfaces unchanged.
    route = await pick_route(model)
    logger.info(
        "llm route: model=%s tier=%s cache_key=%s",
        model,
        route.service_tier or "primary",
        cache_key,
    )
    if route.service_tier is not None:
        flex_client = client.with_options(timeout=route.timeout)
        try:
            response = await flex_client.responses.create(
                service_tier=route.service_tier, **kwargs
            )
            return response.output_text
        except (APITimeoutError, APIStatusError) as exc:
            if not _flex_unavailable(exc):
                raise
            logger.warning(
                "flex call failed (cache_key=%s): %r — marking flex down and "
                "falling back to the primary tier in this call",
                cache_key,
                exc,
            )
            await report_unavailable(route)

    response = await client.responses.create(**kwargs)
    return response.output_text
