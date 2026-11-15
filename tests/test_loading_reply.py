import asyncio

from domain.analysis import FoodAnalysis
from presenters.photo_reply import format_photo_reply_rich
from workflows.loading_reply import Reply, finish_loading


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
