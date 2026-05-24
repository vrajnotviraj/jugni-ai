import json
from typing import Any

from ai.json_parsing import parse_fenced_json
from domain.day import DayNote
from summary_analyser.prompts import GENERAL_DAY_NOTE_FALLBACK


def parse_day_note(raw_text: str) -> DayNote:
    try:
        payload = parse_fenced_json(raw_text)
    except json.JSONDecodeError:
        return DayNote(summary=GENERAL_DAY_NOTE_FALLBACK, health_score=5)

    summary = str(payload.get("summary") or payload.get("note") or "").strip()
    if not summary:
        summary = GENERAL_DAY_NOTE_FALLBACK

    raw_score = payload.get("health_score", 5)
    try:
        health_score = int(raw_score)
    except (TypeError, ValueError):
        health_score = 5
    health_score = max(1, min(10, health_score))

    return DayNote(summary=summary, health_score=health_score)


def parse_rerank_scores(
    raw_text: str,
    *,
    fallback: dict[str, int],
) -> dict[str, int]:
    try:
        payload = parse_fenced_json(raw_text)
    except json.JSONDecodeError:
        return dict(fallback)

    rankings: Any = payload.get("rankings")
    if not isinstance(rankings, list):
        return dict(fallback)

    result = dict(fallback)
    for entry in rankings:
        if not isinstance(entry, dict):
            continue
        label = entry.get("sender_label")
        if not isinstance(label, str) or label not in result:
            continue
        raw_score = entry.get("health_score")
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            continue
        result[label] = max(1, min(10, score))
    return result
