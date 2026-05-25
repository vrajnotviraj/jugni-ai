from html import escape

MEAL_UPDATED_PARSE_MODE = "HTML"


def format_meal_updated(
    *,
    sender_label: str,
    dish: str,
    previous_calories: int,
    new_calories: int,
    new_total_calories: int,
    day_key: str,
    today_key: str,
) -> str:
    name = escape(sender_label, quote=False) if sender_label else "Someone"
    dish_text = escape(dish, quote=False) if dish else "meal"
    delta = new_calories - previous_calories
    delta_sign = "+" if delta >= 0 else "−"
    delta_text = f"{delta_sign}{abs(delta)} kcal"
    total_label = "Today's total" if day_key == today_key else f"Total for {day_key}"
    return (
        f"✏️ <b>{name}'s meal updated</b>\n"
        f"Dish: {dish_text}\n"
        f"Calories: {previous_calories} → {new_calories} kcal ({delta_text})\n"
        f"{total_label}: {new_total_calories} kcal"
    )
