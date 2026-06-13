"""Coaching: the subjective, friendly line written after the plate is read.

This half decides for itself what is worth saying about a logged meal -- a fun
fact, honest praise, or one concrete tweak -- given the extracted macros and the
person's day. It never changes the numbers; the objective read lives in
``analyzers.image.extraction``.
"""

from analyzers.image.coaching.parser import (
    CoachingParseError,
    fallback_coaching_tip,
    parse_coaching_tip,
)
from analyzers.image.coaching.prompts import (
    FOOD_COACHING_RESPONSE_FORMAT,
    FOOD_COACHING_SYSTEM_PROMPT,
    food_coaching_user_prompt,
)

__all__ = [
    "CoachingParseError",
    "FOOD_COACHING_RESPONSE_FORMAT",
    "FOOD_COACHING_SYSTEM_PROMPT",
    "fallback_coaching_tip",
    "food_coaching_user_prompt",
    "parse_coaching_tip",
]
