import logging

from openai import APIStatusError, APITimeoutError, AsyncOpenAI

from llm.smart_router import pick_route, report_unavailable

logger = logging.getLogger(__name__)

# Models on the GPT-5.6+ caching API (prompt_cache_options.ttl).
_TTL_CACHE_PREFIXES = ("gpt-6", "gpt-5.6")
# Reasoning models that accept the `reasoning` parameter.
_REASONING_PREFIXES = ("gpt-5", "gpt-6", "o3", "o4")


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
    response_format: dict[str, object] | None = None,
    cache_key: str | None = None,
) -> str:
    # OpenAI prompt caching is automatic for prompts >= 1024 tokens and works on an
    # exact-prefix match. Keep all static content (the large system prompt) at the
    # front and every dynamic part (the user text and the image) last, so the
    # stable prefix is reused across requests. Do not interpolate per-request values
    # (caption, time, prior meals, the image) into `system` or the cache is busted
    # on every call.
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
    if response_format:
        kwargs["text"] = {"format": response_format}
    # `prompt_cache_key` makes routing sticky so same-type requests land on the same
    # warm engine (on GPT-5.6+ it also splits cache accounting per call type).
    if cache_key:
        kwargs["prompt_cache_key"] = cache_key
    # Long cache lifetime matters for a bot that receives photos sporadically
    # through the day. GPT-5.6+ (incl. gpt-6-luna) replaced prompt_cache_retention
    # with prompt_cache_options.ttl ("30m" default, or "12h"); older models take
    # "24h". extra_body: the installed SDK predates prompt_cache_options.
    if model.startswith(_TTL_CACHE_PREFIXES):
        kwargs["extra_body"] = {"prompt_cache_options": {"ttl": "12h"}}
    else:
        kwargs["prompt_cache_retention"] = "24h"
    # Reasoning models default to medium effort; low keeps cost and latency down
    # for these extraction-style calls. Non-reasoning models (gpt-4.1) reject it.
    if model.startswith(_REASONING_PREFIXES):
        kwargs["reasoning"] = {"effort": "low"}

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
        # max_retries=0: a flex timeout means flex is congested, so the SDK's
        # default retries would just re-hit the same slow lane and stack another
        # full timeout each (45s -> ~135s before we ever fall back). One attempt,
        # then trip the breaker and fall through to primary.
        flex_client = client.with_options(timeout=route.timeout, max_retries=0)
        try:
            response = await flex_client.responses.create(
                service_tier=route.service_tier, **kwargs
            )
            _log_usage(response, cache_key)
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
    _log_usage(response, cache_key)
    return response.output_text


def _log_usage(response: object, cache_key: str | None) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    details = getattr(usage, "input_tokens_details", None)
    logger.info(
        "llm usage: cache_key=%s input=%s cached=%s output=%s",
        cache_key,
        usage.input_tokens,
        getattr(details, "cached_tokens", 0),
        usage.output_tokens,
    )
