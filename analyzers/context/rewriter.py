import logging
from collections.abc import Callable, Coroutine
from typing import Any

from openai import AsyncOpenAI

from analyzers.context.prompts import (
    CONTEXT_REWRITE_SYSTEM_PROMPT,
    context_rewrite_user_prompt,
)
from core.settings import Settings
from llm.json_parsing import parse_fenced_json
from llm.openai_client import call_responses

logger = logging.getLogger(__name__)

# Mirror the storage bounds so the rewritten set always fits what we persist.
_NOTE_MAX_LEN = 120
_MAX_NOTES = 25

ContextRewriter = Callable[..., Coroutine[Any, Any, list[str]]]


def build_context_rewriter(
    settings: Settings,
    client: AsyncOpenAI | None = None,
) -> ContextRewriter:
    openai_client = client or AsyncOpenAI(api_key=settings.openai_api_key)
    model = settings.openai_model

    async def rewriter(*, existing: list[str], new_note: str) -> list[str]:
        return await rewrite_context(
            openai_client, model=model, existing=existing, new_note=new_note
        )

    return rewriter


async def rewrite_context(
    client: AsyncOpenAI,
    *,
    model: str,
    existing: list[str],
    new_note: str,
) -> list[str]:
    """Merge new_note into existing notes and return a concise, deduped set.

    Never raises: on any failure it falls back to appending the new note to the
    existing notes (deduped), so the user's note is never silently lost.
    """
    try:
        raw = await call_responses(
            client,
            model=model,
            system=CONTEXT_REWRITE_SYSTEM_PROMPT,
            user=context_rewrite_user_prompt(existing=existing, new_note=new_note),
            cache_key="context-rewrite",
        )
        payload = parse_fenced_json(raw)
    except Exception:
        logger.exception("context rewrite failed; falling back to append")
        return _fallback_append(existing, new_note)

    notes = payload.get("notes")
    if not isinstance(notes, list):
        logger.info("context rewrite: model returned no notes list, falling back")
        return _fallback_append(existing, new_note)

    cleaned = _clean(str(note) for note in notes)
    if not cleaned:
        logger.info("context rewrite: empty after cleaning, falling back")
        return _fallback_append(existing, new_note)

    logger.info(
        "context rewrite ok existing=%s -> result=%s", len(existing), len(cleaned)
    )
    return cleaned


def _fallback_append(existing: list[str], new_note: str) -> list[str]:
    """Degrade to old behaviour: keep existing, add the new note if not a dupe."""
    return _clean([*existing, new_note])


def _clean(notes: Any) -> list[str]:
    """Trim, length-cap, drop blanks and case-insensitive dupes, cap the count."""
    result: list[str] = []
    seen: set[str] = set()
    for note in notes:
        text = note.strip()[:_NOTE_MAX_LEN].strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= _MAX_NOTES:
            break
    return result
