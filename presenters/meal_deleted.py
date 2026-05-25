from html import escape

MEAL_DELETED_PARSE_MODE = "HTML"


def format_meal_deleted(
    *,
    sender_label: str,
    dish: str,
    calories: int,
    new_total_calories: int,
    day_key: str,
    today_key: str,
) -> str:
    name = escape(sender_label, quote=False) if sender_label else "Someone"
    dish_text = escape(dish, quote=False) if dish else "meal"
    total_label = "Today's total" if day_key == today_key else f"Total for {day_key}"
    return (
        f"🗑️ <b>{name}'s meal removed</b>\n"
        f"Dish: {dish_text}\n"
        f"Calories: −{calories} kcal\n"
        f"{total_label}: {new_total_calories} kcal"
    )
