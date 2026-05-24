from domain.analysis import FoodAnalysis

NOT_FOOD_REPLY = "Doesn't look like food. Send a food photo to get a calorie estimate."


def format_photo_reply(
    sender_label: str,
    analysis: FoodAnalysis,
    daily_total: int,
) -> str:
    if not analysis.is_food:
        return NOT_FOOD_REPLY

    header = f"{sender_label} — {analysis.dish}"
    totals = (
        f"{analysis.calories} kcal · {analysis.confidence} · "
        f"today: {daily_total} kcal"
    )
    return f"{header}\n{totals}\n{analysis.tip}"
