import asyncio
import json
import zlib

from domain.analysis import FoodAnalysis
from presenters.photo_reply import (
    MEAL_WIDGET,
    format_photo_reply_rich,
    format_photo_widget_data,
)
from workflows.loading_reply import (
    LOADING_WIDGET,
    Reply,
    finish_loading,
    start_loading,
    update_loading,
)


class FakeTelegram:
    def __init__(self, rich_fails: bool = False) -> None:
        self.rich_fails = rich_fails
        self.calls: list[tuple] = []

    async def send_rich_message(self, chat_id, html, reply_to=None):
        if self.rich_fails:
            raise RuntimeError("Bad Request: can't parse rich message")
        self.calls.append(("rich", html))

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append(("text", text))

    async def delete_message(self, chat_id, message_id):
        self.calls.append(("delete", message_id))


MEAL = FoodAnalysis(
    dish="Dal & <rice>",
    calories=620,
    confidence="medium",
    tip="Add curd for protein.",
    is_food=True,
    protein_g=22,
    carb_g=90,
    fat_g=18,
    items=("2 rotli ~160", "dal katori ~190"),
)


def test_rich_card_renders_table_bars_and_escapes_text():
    html = format_photo_reply_rich(
        "Vraj",
        MEAL,
        1240,
        eaten_at="13:05",
        calorie_target=2000,
        protein_today_g=58,
        protein_target_g=120,
    )
    assert "<h3>" in html and "<table bordered striped>" in html
    assert "Dal &amp; &lt;rice&gt;" in html
    assert "620" in html and "22g · 14%" in html
    assert "▰▰▰▰▰▰▱▱▱▱ 62%" in html
    assert "<details><summary>What's in it</summary>" in html


def test_rich_card_is_none_for_non_food():
    not_food = FoodAnalysis(
        dish="", calories=0, confidence="low", tip="", is_food=False
    )
    assert format_photo_reply_rich("Vraj", not_food, 0) is None


def test_finish_sends_rich_then_deletes_placeholder():
    tg = FakeTelegram()
    asyncio.run(finish_loading(tg, 1, 10, 99, Reply("plain", "<h3>x</h3>")))
    assert tg.calls == [("rich", "<h3>x</h3>"), ("delete", 99)]


def test_finish_keeps_placeholder_when_every_send_fails():
    class AllFail(FakeTelegram):
        async def send_message(self, chat_id, text, **kwargs):
            raise RuntimeError("telegram down")

    tg = AllFail(rich_fails=True)
    asyncio.run(finish_loading(tg, 1, 10, 99, Reply("plain", "<h3>x</h3>")))
    assert tg.calls == []


def test_finish_sends_classic_with_preview_when_no_rich():
    sent = {}

    class Recording(FakeTelegram):
        async def send_message(self, chat_id, text, **kwargs):
            sent.update(kwargs)
            self.calls.append(("text", text))

    tg = Recording()
    preview = {"is_disabled": False}
    asyncio.run(finish_loading(tg, 1, 10, 99, Reply("plain", None, preview)))
    assert tg.calls == [("text", "plain"), ("delete", 99)]
    assert sent["parse_mode"] == "HTML"
    assert sent["link_preview_options"] == preview
    assert sent["reply_to_message_id"] == 10


def test_finish_falls_back_to_classic_when_rich_fails():
    tg = FakeTelegram(rich_fails=True)
    asyncio.run(finish_loading(tg, 1, 10, 99, Reply("plain", "<h3>x</h3>")))
    assert tg.calls == [("text", "plain"), ("delete", 99)]


# --- Bot API 10.4 widgets ---------------------------------------------------


class WidgetTelegram(FakeTelegram):
    def __init__(self, widget_fails: bool = False) -> None:
        super().__init__()
        self.widget_fails = widget_fails

    async def send_widget(self, chat_id, html, chat_data=None, reply_to=None):
        if self.widget_fails:
            raise RuntimeError("Bad Request: widgets are not allowed")
        self.calls.append(("widget", chat_data))
        return 7

    async def edit_message_widget_data(self, chat_id, message_id, chat_data):
        self.calls.append(("widget_edit", json.loads(chat_data)))

    async def send_animation(self, chat_id, path, caption, reply_to=None):
        self.calls.append(("gif", caption))
        return 8

    async def edit_message_caption(self, chat_id, message_id, caption):
        self.calls.append(("caption", caption))


CARD = Reply("plain", "<h3>x</h3>", widget=(MEAL_WIDGET, '{"dish":"x"}'))


def test_widgets_fit_bot_api_size_limit():
    for html in (LOADING_WIDGET, MEAL_WIDGET):
        assert len(zlib.compress(html.encode(), 9)) <= 4096


def test_private_chat_gets_widget_card():
    tg = WidgetTelegram()
    asyncio.run(finish_loading(tg, 1, 10, 99, CARD))
    assert tg.calls == [("widget", '{"dish":"x"}'), ("delete", 99)]


def test_group_chat_skips_widget():
    tg = WidgetTelegram()
    asyncio.run(finish_loading(tg, -100, 10, 99, CARD))
    assert tg.calls == [("rich", "<h3>x</h3>"), ("delete", 99)]


def test_widget_failure_falls_back_to_rich():
    tg = WidgetTelegram(widget_fails=True)
    asyncio.run(finish_loading(tg, 1, 10, 99, CARD))
    assert tg.calls == [("rich", "<h3>x</h3>"), ("delete", 99)]


def test_loader_is_widget_in_dm_gif_in_group():
    tg = WidgetTelegram()
    assert asyncio.run(start_loading(tg, 1, 10, "🔍 Analysing…")) == 7
    assert asyncio.run(start_loading(tg, -100, 10, "🔍 Analysing…")) == 8
    asyncio.run(update_loading(tg, 1, 7, MEAL))
    asyncio.run(update_loading(tg, -100, 8, MEAL))
    assert tg.calls[2] == (
        "widget_edit",
        {"label": "Writing your tip", "dish": MEAL.dish, "kcal": 620},
    )
    assert tg.calls[3][0] == "caption"


def test_widget_data_trims_to_1024_bytes():
    long = FoodAnalysis(
        dish="Thali",
        calories=900,
        confidence="high",
        tip="Eat more greens. " * 60,
        is_food=True,
        protein_g=30,
        carb_g=120,
        fat_g=30,
        items=tuple(f"item number {i} ~100 kcal" for i in range(40)),
    )
    data = format_photo_widget_data("Vraj", long, 1500, calorie_target=2000)
    assert len(data.encode()) <= 1024
    parsed = json.loads(data)
    assert parsed["dish"] == "Thali" and parsed["goal"] == 2000
    assert "items" not in parsed or len(parsed["items"]) < 40
    assert format_photo_widget_data("Vraj", MEAL, 0) is not None
