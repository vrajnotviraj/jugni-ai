"""Shared macro-balance rendering used by both the photo reply and the daily
summary, so the two surfaces show the plate's balance the same way.

The balance is expressed as each macro's share of calories (a shape, not a
precise number) using the Atwater factors 4/4/9 kcal per gram, the global
standard for converting macro grams to energy.
"""

# (label, kcal per gram, icon) for the three energy macros.
_MACROS = (
    ("Protein", 4, "💪"),
    ("Carbs", 4, "🍚"),
    ("Fat", 9, "🧈"),
)


def macro_shares(
    protein_g: int, carb_g: int, fat_g: int
) -> list[tuple[str, str, int]] | None:
    """Ranked ``(label, icon, percent-of-calories)`` for protein, carbs, and fat,
    largest share first. Returns ``None`` when there is no macro energy to show
    (all three are zero), so callers can omit the line entirely rather than
    render a meaningless row of zeros.
    """
    grams = (protein_g, carb_g, fat_g)
    energy = [g * kcal for (_, kcal, _), g in zip(_MACROS, grams, strict=True)]
    if sum(energy) <= 0:
        return None
    shares = _to_percent(energy)
    ranked = sorted(
        zip(_MACROS, shares, strict=True), key=lambda pair: pair[1], reverse=True
    )
    return [(label, icon, pct) for (label, _, icon), pct in ranked]


def _to_percent(values: list[int]) -> list[int]:
    """Whole-number percentages that always sum to 100 (largest-remainder)."""
    total = sum(values)
    raw = [v / total * 100 for v in values]
    floored = [int(x) for x in raw]
    leftover = 100 - sum(floored)
    by_remainder = sorted(
        range(len(values)), key=lambda i: raw[i] - floored[i], reverse=True
    )
    for i in by_remainder[:leftover]:
        floored[i] += 1
    return floored
