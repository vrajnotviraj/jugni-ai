import asyncio

from domain.day import DayMacros, DayReport, MealTimeline, UserDaySummary
from presenters.day_summary import format_day_summary_rich
from workflows.send_day_report import send_day_report

USER = UserDaySummary(
    sender_label="A & <B>",
    calories=1840,
    dishes=("dal",),
    meals_timeline=(MealTimeline(time="13:05", dish="Dal rice", calories=620),),
    summary="Solid protein day.",
    health_score=8,
    rank=1,
    meal_periods_covered=3,
    macros=DayMacros(protein_g=90, carb_g=200, fat_g=60),
    streak=5,
)
REPORT = DayReport(chat_id=-1, day_key="2026-11-15", total_photos=3, users=(USER,))


class FakeTelegram:
    def __init__(self, rich_fails: bool = False) -> None:
        self.rich_fails = rich_fails
        self.calls: list[tuple[str, str]] = []

    async def send_rich_message(self, chat_id, html, reply_to=None):
        if self.rich_fails:
            raise RuntimeError("rich unsupported")
        self.calls.append(("rich", html))

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append(("text", text))


def test_rich_summary_has_leaderboard_row_and_details():
    html = format_day_summary_rich(REPORT)
    assert "<table bordered striped>" in html
    assert "<td>A &amp; &lt;B&gt;</td>" in html
    assert "💚 8/10" in html and "🔥 5d" in html and "3/3" in html
    assert "<details><summary>🥇 A &amp; &lt;B&gt; · 1840 kcal</summary>" in html
    assert "<code>13:05</code> Dal rice — 620 kcal" in html


def test_rich_summary_is_none_without_users():
    empty = DayReport(chat_id=-1, day_key="2026-11-15", total_photos=0, users=())
    assert format_day_summary_rich(empty) is None


def test_send_day_report_prefers_rich_and_falls_back_to_chunks():
    tg = FakeTelegram()
    asyncio.run(send_day_report(telegram=tg, report=REPORT))
    assert [kind for kind, _ in tg.calls] == ["rich"]

    tg = FakeTelegram(rich_fails=True)
    asyncio.run(send_day_report(telegram=tg, report=REPORT))
    assert [kind for kind, _ in tg.calls] == ["text"]
    assert "Healthiest eaters today" in tg.calls[0][1]
