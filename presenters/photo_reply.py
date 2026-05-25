from html import escape

from domain.analysis import FoodAnalysis

NOT_FOOD_REPLY = "Doesn't look like food. Send a food photo to get a calorie estimate."

PHOTO_REPLY_PARSE_MODE = "HTML"

_CONFIDENCE_ICONS = {"medium": "⚖️", "low": "❓"}


def format_photo_reply(
    sender_label: str,
    analysis: FoodAnalysis,
    daily_total: int,
) -> str:
    if not analysis.is_food:
        return NOT_FOOD_REPLY

    header = f"{_dish_icon(analysis.dish)} <b>{escape(sender_label, quote=False)}'s meal</b>"
    dish_line = f"Dish: {escape(analysis.dish, quote=False)}"
    calories_line = f"{_calorie_icon(analysis.calories)} Calories: {analysis.calories} kcal"
    today_line = f"{_day_progress_icon(daily_total)} Today's total: {daily_total} kcal"
    confidence_line = _confidence_line(analysis.confidence)

    parts = [header, dish_line, calories_line, today_line, confidence_line]

    tip = (analysis.tip or "").strip()
    if tip:
        parts.append(f"<blockquote>{escape(tip, quote=False)}</blockquote>")
    return "\n".join(parts)


def _confidence_line(confidence: str) -> str:
    icon = _CONFIDENCE_ICONS.get(confidence)
    prefix = f"{icon} " if icon else ""
    return f"{prefix}Confidence: {confidence}"


_CALORIE_TIERS = (
    (200, "🌱"),
    (450, "🍴"),
    (750, "🔥"),
    (1100, "💥"),
)
_CALORIE_HEAVY_ICON = "🚨"


def _calorie_icon(calories: int) -> str:
    for threshold, icon in _CALORIE_TIERS:
        if calories < threshold:
            return icon
    return _CALORIE_HEAVY_ICON


_DAY_PROGRESS_TIERS = (
    (600, "🌅"),
    (1400, "🌤️"),
    (2200, "🌇"),
    (2800, "🌙"),
)
_DAY_PROGRESS_OVER_ICON = "⚠️"


def _day_progress_icon(daily_total: int) -> str:
    for threshold, icon in _DAY_PROGRESS_TIERS:
        if daily_total < threshold:
            return icon
    return _DAY_PROGRESS_OVER_ICON


_DISH_KEYWORDS = (
    (("salad", "greens", "lettuce", "spinach"), "🥗"),
    (("soup", "broth", "stew"), "🍲"),
    (("burger",), "🍔"),
    (("pizza",), "🍕"),
    (("pasta", "noodle", "ramen", "spaghetti"), "🍝"),
    (("sushi", "sashimi"), "🍣"),
    (("rice", "biryani", "pulao", "chawal"), "🍚"),
    (("dal", "curry", "sabzi", "sambar"), "🍛"),
    (("roti", "naan", "paratha", "chapati", "bread", "toast", "sandwich"), "🥪"),
    (("egg", "omelette", "omelet"), "🍳"),
    (("chicken", "fish", "meat", "lamb", "mutton", "beef", "pork", "kebab"), "🍗"),
    (("fruit", "apple", "banana", "mango", "berry", "orange"), "🍎"),
    (("cake", "cookie", "brownie", "dessert", "ice cream", "icecream", "chocolate", "sweet"), "🍰"),
    (("tea", "coffee", "chai", "latte"), "☕"),
    (("milk", "lassi", "smoothie", "shake", "juice"), "🥛"),
)
_DISH_DEFAULT_ICON = "🍽️"


def _dish_icon(dish: str) -> str:
    needle = dish.lower()
    for keywords, icon in _DISH_KEYWORDS:
        if any(word in needle for word in keywords):
            return icon
    return _DISH_DEFAULT_ICON
