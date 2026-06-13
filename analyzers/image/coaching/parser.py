import json

from analyzers.image.coaching.prompts import GENERAL_TIP_FALLBACK
from domain.analysis import CoachingTip
from llm.json_parsing import parse_fenced_json


class CoachingParseError(RuntimeError):
    pass


def parse_coaching_tip(raw_text: str) -> CoachingTip:
    try:
        payload = parse_fenced_json(raw_text)
    except json.JSONDecodeError as error:
        raise CoachingParseError(
            f"OpenAI response was not valid coaching JSON: {raw_text[:200]}"
        ) from error
    if not isinstance(payload, dict):
        raise CoachingParseError("OpenAI coaching response was not an object.")

    tip = _clean_text(payload.get("tip"))
    if not tip:
        raise CoachingParseError("OpenAI coaching response had invalid fields.")
    return CoachingTip(tip=tip)


def fallback_coaching_tip() -> CoachingTip:
    return CoachingTip(tip=GENERAL_TIP_FALLBACK)


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.translate(
        str.maketrans(
            {"’": "'", "‘": "'", "“": '"', "”": '"', "‑": "-", "–": "-", "—": "-"}
        )
    ).strip()
