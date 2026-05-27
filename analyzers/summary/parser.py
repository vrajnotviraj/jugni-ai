import json

from analyzers.summary.prompts import GENERAL_DAY_NOTE_FALLBACK
from domain.scoring import FoodSignals
from llm.json_parsing import parse_fenced_json


def parse_day_signals(raw_text: str) -> tuple[str, FoodSignals]:
    """Parse the model's summary text and detected food signals. Scoring is done
    downstream in code, so a parse failure yields neutral signals, not a score."""
    try:
        payload = parse_fenced_json(raw_text)
    except json.JSONDecodeError:
        return GENERAL_DAY_NOTE_FALLBACK, FoodSignals()

    summary = str(payload.get("summary") or payload.get("note") or "").strip()
    if not summary:
        summary = GENERAL_DAY_NOTE_FALLBACK

    signals = FoodSignals(
        veg_servings=_int(payload.get("veg_servings")),
        has_legume=bool(payload.get("has_legume")),
        has_whole_grain=bool(payload.get("has_whole_grain")),
        protein_meals=_int(payload.get("protein_meals")),
        has_fruit=bool(payload.get("has_fruit")),
        has_plain_dairy=bool(payload.get("has_plain_dairy")),
        fried_items=_int(payload.get("fried_items")),
        sweet_items=_int(payload.get("sweet_items")),
        ultraprocessed_items=_int(payload.get("ultraprocessed_items")),
        refined_grain_dominant=bool(payload.get("refined_grain_dominant")),
    )
    return summary, signals


def _int(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
