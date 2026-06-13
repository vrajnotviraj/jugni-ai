"""The eval scenarios — each one reads top-to-bottom as the steps it performs.

A `Day` wraps the low-level `World` with friendly, self-printing actions
(`profile`, `context`, `post`, `delete_one`, `summary`) and picks photos by type,
so a case is just a short sequence of awaits with no plumbing. A case attaches a
judging rule to any tip/summary it cares about (`judge=...`); the runner grades
them later. To add a case: write `async def case_x(day)` and list it in `CASES`.
"""

import random
import re
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path

from domain.analysis import FoodAnalysis
from evals.harness import World

PHOTOS = Path(__file__).parent / "photos"

# Judging rules a case can attach to a tip or summary (graded pass/fail later).
# Each rule is one clear, self-contained statement so the judge cannot misread it.
TIP = "The tip is kind (not preachy) and gives a concrete suggestion that fits this specific dish, not a generic platitude."
VEG = "The tip never recommends eggs, meat, or fish as a food to eat or add (the person is vegetarian and eggless); suggesting they skip or replace such foods is fine."
SPLIT_TIP = "The tip is grounded in the visible plate, respects the user's dietary facts, and does not sound like a generic protein or light-next-meal template."
SUMMARY = "The text describes one person's day with at least one strength and one gap, in plain words, and quotes no raw calorie or gram numbers."

# /intake rules. The card must be grounded in the exact items the user typed.
INTAKE = "The reply is a logged meal card for the typed items: it names both the chocolate and the almonds, shows one total calorie number for the meal, and lists the items under a 'What's in it' breakdown. It is a successful log, not an error or a request for more detail."

# Streak rules. The reply rules embed the exact day-count the seeded history
# must produce, so the judge verifies the streak maths, not just the wording.
STREAK_5 = "The text tells the user they are on a 5-day streak (it states the number 5 as the streak/day count) and encourages them to keep it going."
STREAK_MILESTONE = "The text celebrates a 7-day streak as a milestone with congratulatory wording (e.g. a 'week' achievement), not just a plain count."
STREAK_GRACE = "The text tells the user they are on a 4-day streak (it states the number 4 as the day count) and encourages them to keep going."
NO_STREAK = "The text is a normal meal reply and does NOT mention any streak, consecutive-day count, or 'don't break the chain' language."
SUMMARY_STREAK = "The leaderboard text shows a consecutive-day streak count (a number of days running) for at least one person, alongside their meal stats."
NUDGE_KIND = "The message asks people to log a meal before the day ends to keep their streak alive, in an encouraging, non-shaming tone (no blame or 'you failed' wording)."

# /recommend rules. Each grades one behaviour of the recommendation reply.
REC_VEG = "Every suggested meal option is vegetarian and egg-free: no eggs, meat, chicken, or fish appear in any suggested dish."
REC_PROTEIN = "The text includes a line that references what was actually eaten today (a dish by name or its carb-heavy, low-protein character), most suggested options are protein-forward, no gram numbers are quoted, and every calorie figure is a range rather than one exact number."
REC_NO_SWEETS = "No suggested option is a dessert, mithai, or sweetened drink, and the text never encourages more sugar. Plain whole fruit does not count as a sweet."
REC_EAT_SOMETHING = "The text encourages eating a sensible meal. It never suggests skipping a meal, fasting, a detox, or going without food; suggesting lighter dishes or moderate portions within a real meal is fine."
REC_GAIN = "The options suit a muscle-gain goal: protein-forward with adequate calories, with no starvation or restriction framing."
REC_GROUP_PRIVATE = "The text contains no body measurements (weight, height, age, sex), no daily calorie or protein target NUMBERS, no remaining-calorie-budget numbers, and no mention of any health condition (such as diabetes) or medical reasoning. Qualitative gap language ('protein is still low', 'fills the protein gap'), percentages, and the dishes already eaten today are all fine — only explicit numbers and health conditions fail."
REC_REQUEST = "The reply visibly answers the user's specific ask to avoid oily or greasy food: no deep-fried or oil-heavy dish is suggested, at least one line acknowledges that ask, and the options are meaningfully different dishes rather than three near-identical variations with the same calorie range."

# Photos are tagged by filename: s_ = snack, m_ = meal. Times come from these windows.
SNACK_WINDOWS = [(7, 10), (15, 17)]  # 7-11 AM, 3-6 PM
MEAL_WINDOWS = [(12, 14), (19, 21)]  # 12-3 PM, 7-10 PM


def photos(kind: str = "") -> list[Path]:
    return sorted(
        p
        for p in PHOTOS.glob(f"{kind}*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


class Day:
    """A simulated day. Each method is one printed step in a case's sequence."""

    def __init__(self, world: World, rng: random.Random) -> None:
        self._world = world
        self._rng = rng
        self._step_no = 0
        self._ids: dict[str, int] = {}
        self.to_judge: list[tuple[str, str, str]] = []

    def snack(self) -> Path:
        return self._rng.choice(photos("s_"))

    def meal(self) -> Path:
        return self._rng.choice(photos("m_"))

    async def seed(self, user: str, days_ago: list[int]) -> None:
        """Give a user prior logged days, so today's post sits on a real streak.

        Each entry is a number of days before today; activity is written
        directly (no vision call), the way multi-day history is simulated."""
        tz = self._world.settings.timezone
        today = datetime.now(tz).date()
        for offset in days_ago:
            when = datetime.combine(today - timedelta(days=offset), dtime(12, 0), tz)
            await self._world.seed_meal(label=user, user_id=self._id(user), when=when)
        self._say(f"{user} has prior activity {sorted(days_ago)} day(s) ago")

    async def profile(self, user: str, text: str) -> None:
        reply = await self._world.command(
            user_id=self._id(user), text=f"/profile {text}"
        )
        self._say(f"{user} sets a profile: {text}")
        self._say("↳ " + _reply(reply))

    async def context(self, user: str, text: str) -> None:
        reply = await self._world.command(
            user_id=self._id(user), text=f"/context {text}"
        )
        self._say(f"{user} sends a context message: {text}")
        self._say("↳ " + _reply(reply))

    async def post(
        self,
        user: str,
        photo: Path,
        *,
        judge: str | None = None,
        judge_reply: str | None = None,
        show: bool = True,
    ) -> None:
        when = self._time(photo)
        try:
            result = await self._world.upload(
                photo, label=user, user_id=self._id(user), time=when
            )
        except Exception as error:  # a transient vision failure shouldn't sink the case
            self._say(f"{user} posts {photo.name} at {when}: upload failed ({error})")
            return
        analysis = result["analysis"]
        if not analysis["is_food"]:
            return
        tip = (analysis["tip"] or "").strip()
        if show:
            self._say(
                f"{user} posts at {when}: {analysis['dish']} · {analysis['calories']} kcal"
            )
            print(f"        tip: {tip or '(no tip)'}")
        # Every food plate should get a coaching line now; judge even an empty
        # tip so a regression that drops the line fails the grader loudly instead
        # of slipping past it.
        if judge:
            self.to_judge.append((f"tip · {analysis['dish']}", tip, judge))
        if judge_reply:
            reply = _plain(result.get("reply_text", ""))
            self.to_judge.append((f"reply · {analysis['dish']}", reply, judge_reply))

    async def seed_dish(
        self,
        user: str,
        dish: str,
        kcal: int,
        *,
        protein: int = 0,
        carb: int = 0,
        fibre: int = 0,
        sugar: int = 0,
        days_ago: int = 0,
        at_hour: int = 12,
    ) -> None:
        """Store a fully-analysed meal directly (no vision call), so recommend
        cases can shape a day's macros deterministically."""
        tz = self._world.settings.timezone
        when = datetime.combine(
            datetime.now(tz).date() - timedelta(days=days_ago), dtime(at_hour, 0), tz
        )
        analysis = FoodAnalysis(
            dish=dish,
            calories=kcal,
            confidence="high",
            tip="",
            is_food=True,
            protein_g=protein,
            carb_g=carb,
            fibre_g=fibre,
            added_sugar_g=sugar,
        )
        await self._world.seed_meal(
            label=user, user_id=self._id(user), when=when, analysis=analysis
        )
        ago = "today" if not days_ago else f"{days_ago}d ago"
        self._say(f"{user} logged {dish} ({kcal} kcal) {ago} at {at_hour}:00")

    async def recommend(
        self,
        user: str,
        text: str = "",
        *,
        group: bool = False,
        judge: str | None = None,
    ) -> str:
        reply = await self._world.recommend(
            user_id=self._id(user),
            text=text,
            username=user.lstrip("@"),
            group=group,
        )
        where = " in the group" if group else ""
        self._say(f"{user} sends /recommend {text}".rstrip() + where)
        if reply:
            print("\n" + _plain(reply) + "\n")
        if judge:
            # An empty reply is judged too, so a dropped command fails loudly.
            self.to_judge.append((f"recommend · {user}", _plain(reply), judge))
        return reply

    async def intake(
        self,
        user: str,
        text: str,
        *,
        group: bool = False,
        judge: str | None = None,
    ) -> str:
        reply = await self._world.intake(
            user_id=self._id(user),
            text=text,
            username=user.lstrip("@"),
            group=group,
        )
        self._say(f"{user} sends /intake {text}")
        if reply:
            print("\n" + _plain(reply) + "\n")
        if judge:
            self.to_judge.append((f"intake · {user}", _plain(reply), judge))
        return reply

    async def delete_one(self, user: str) -> None:
        block = _block(await self._world.meals(), user)
        if not block or not block["meals"]:
            self._say(f"{user} has no stored meals to delete")
            return
        self._say(
            f"{user} has {len(block['meals'])} meals, total {block['total_calories']} kcal"
        )
        result = await self._world.delete(block["meals"][0]["message_id"])
        self._say(f"deleted one meal; new total {result['new_total_calories']} kcal")

    async def summary(self, *, judge: str | None = None) -> None:
        self._say("everyone has posted; building the daily summary")
        data, text = await self._world.summary()
        print("\n" + _plain(text))
        if judge:
            self.to_judge.append(("summary", _plain(text), judge))
            return
        for user in data["users"][:2]:
            if user["summary"]:
                self.to_judge.append(
                    (f"summary · {user['sender_label']}", user["summary"], SUMMARY)
                )

    async def nudge(self, *, judge: str | None = None) -> None:
        self._say("evening: checking who is at risk of breaking their streak")
        at_risk, text = await self._world.nudge()
        self._say(f"at risk: {[user.sender_label for user in at_risk]}")
        if text:
            print("\n" + _plain(text))
        if judge and text:
            self.to_judge.append(("nudge", _plain(text), judge))

    def _say(self, text: str) -> None:
        self._step_no += 1
        print(f"  {self._step_no}. {text}")

    def _id(self, user: str) -> int:
        if user not in self._ids:
            self._ids[user] = self._world.user_id(len(self._ids))
        return self._ids[user]

    def _time(self, photo: Path) -> str:
        windows = SNACK_WINDOWS if photo.name.lower().startswith("s_") else MEAL_WINDOWS
        low, high = self._rng.choice(windows)
        return f"{self._rng.randint(low, high):02d}:{self._rng.choice(['00', '30'])}"


def _reply(result: dict) -> str:
    replies = result.get("replies") or []
    return _plain(replies[0]).splitlines()[0] if replies else "(no reply)"


def _block(meals: dict, user: str) -> dict | None:
    return next((u for u in meals["users"] if u["sender_label"] == user), None)


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


# --------------------------------------------------------------------------- #
# Cases — each is a clear sequence of steps.
# --------------------------------------------------------------------------- #
async def case_profile(day: Day) -> None:
    """A vegetarian, fat-loss user posts a snack and a meal; every tip must fit the diet."""
    await day.profile("@aarav", "vegetarian, no eggs, want to lose fat")
    await day.post("@aarav", day.snack(), judge=VEG)
    await day.post("@aarav", day.meal(), judge=VEG)


async def case_context(day: Day) -> None:
    """A user says they take whole milk, then posts a snack and a meal."""
    await day.context("@diya", "I always take whole milk in my chai and coffee")
    await day.post("@diya", day.snack(), judge=TIP)
    await day.post("@diya", day.meal(), judge=TIP)


async def case_image_split(day: Day) -> None:
    """A personalized photo run exercises split extraction and text-only coaching."""
    from analyzers.image.coaching import FOOD_COACHING_SYSTEM_PROMPT
    from analyzers.image.extraction import FOOD_EXTRACTION_SYSTEM_PROMPT

    day._say(
        "split analyzer expected calls: food photo = 1 vision extraction + 1 text "
        "coaching (the coaching model decides the angle itself); non-food = 1 vision extraction"
    )
    day._say(
        "prompt chars: "
        f"extraction={len(FOOD_EXTRACTION_SYSTEM_PROMPT)}, "
        f"coaching={len(FOOD_COACHING_SYSTEM_PROMPT)}"
    )
    await day.profile("@aarav", "vegetarian, no eggs, want to lose fat")
    await day.seed_dish("@aarav", "Poha with peanuts", 350, protein=9, carb=55)
    await day.post("@aarav", day.meal(), judge=SPLIT_TIP)


async def case_delete(day: Day) -> None:
    """Post two meals, then delete one through the meals route; the total recomputes."""
    await day.post("@kabir", day.meal())
    await day.post("@kabir", day.meal())
    await day.delete_one("@kabir")


async def case_day(day: Day) -> None:
    """Three people each post two meals and a snack (one is vegetarian); grade the summary."""
    await day.profile("@aarav", "vegetarian, no eggs, want to lose fat")
    for user in ("@aarav", "@diya", "@meera"):
        await day.post(user, day.meal(), show=False)
        await day.post(user, day.meal(), show=False)
        await day.post(user, day.snack(), show=False)
    await day.summary()


async def case_streak_reply(day: Day) -> None:
    """A user with 4 prior days logs today: the reply shows a 5-day streak, and a second meal the same day does not repeat it."""
    await day.seed("@aarav", days_ago=[1, 2, 3, 4])
    await day.post("@aarav", day.meal(), judge_reply=STREAK_5)
    await day.post("@aarav", day.meal(), judge_reply=NO_STREAK)


async def case_streak_milestone(day: Day) -> None:
    """A user with 6 prior days logs today; the reply celebrates the 7-day milestone."""
    await day.seed("@diya", days_ago=[1, 2, 3, 4, 5, 6])
    await day.post("@diya", day.meal(), judge_reply=STREAK_MILESTONE)


async def case_streak_grace(day: Day) -> None:
    """A user missed one day but logged around it; today's reply keeps a 4-day streak alive (never-miss-twice)."""
    # Active 1, 3, 4 days ago (single gap at day 2) plus today => length 4.
    await day.seed("@kabir", days_ago=[1, 3, 4])
    await day.post("@kabir", day.meal(), judge_reply=STREAK_GRACE)


async def case_streak_summary(day: Day) -> None:
    """Two people with running streaks post today; the daily summary shows each one's streak."""
    await day.seed("@aarav", days_ago=[1, 2, 3])
    await day.seed("@diya", days_ago=[1, 2, 3, 4, 5])
    await day.post("@aarav", day.meal(), show=False)
    await day.post("@diya", day.meal(), show=False)
    await day.summary(judge=SUMMARY_STREAK)


async def case_streak_nudge(day: Day) -> None:
    """A user with a live streak logged yesterday but not today; the evening nudge names them, then goes silent once they log."""
    await day.seed("@meera", days_ago=[1, 2, 3])
    await day.nudge(judge=NUDGE_KIND)
    await day.post("@meera", day.meal(), show=False)  # now logged today
    await day.nudge()  # nobody at risk -> no message sent


async def case_intake(day: Day) -> None:
    """A typed meal of simple items is looked up online and logged like a photo."""
    await day.intake(
        "@aarav",
        "2 blocks of dark chocolate and 10 almonds",
        group=True,
        judge=INTAKE,
    )


async def case_intake_routing(day: Day) -> None:
    """A DM is the person's own group: photos, /summary and /delete route through
    the tracking loop, while /profile stays a private command (deterministic)."""
    from telegram.updates import (
        DeleteCommand,
        IntakeCommand,
        PhotoMessage,
        ProfileCommand,
        SummaryCommand,
        parse_update,
    )

    def dm(message: dict) -> dict:
        return {
            "update_id": 0,
            "message": {"date": 1, "chat": {"id": 42, "type": "private"}, **message},
        }

    sender = {"id": 42, "first_name": "Eval"}
    photo = parse_update(dm({"message_id": 1, "from": sender, "photo": [{"file_id": "f", "file_size": 9}]}))
    summary = parse_update(dm({"message_id": 2, "from": sender, "text": "/summary"}))
    profile = parse_update(dm({"message_id": 3, "from": sender, "text": "/profile vegetarian"}))
    delete = parse_update(dm({"message_id": 4, "from": sender, "text": "/delete", "reply_to_message": {"message_id": 1, "photo": [{"file_id": "f"}]}}))
    intake_dm = parse_update(dm({"message_id": 5, "date": 1, "from": sender, "text": "/intake 10g almonds"}))
    intake_group = parse_update({"update_id": 0, "message": {"message_id": 6, "date": 1, "chat": {"id": -100, "type": "supergroup"}, "from": sender, "text": "/intake paneer"}})

    assert isinstance(photo, PhotoMessage), photo
    assert isinstance(summary, SummaryCommand), summary
    assert isinstance(profile, ProfileCommand), profile
    assert isinstance(delete, DeleteCommand), delete
    assert isinstance(intake_dm, IntakeCommand) and intake_dm.surface == "dm", intake_dm
    assert isinstance(intake_group, IntakeCommand) and intake_group.surface == "group", intake_group
    day._say("DM photo/summary/delete route to the group loop; /profile stays private")
    day._say("/intake parses on both surfaces with the right surface tag")


async def case_intake_reject(day: Day) -> None:
    """A low-confidence or non-food typed meal is never stored (deterministic)."""
    from datetime import datetime

    from domain.analysis import FoodAnalysis
    from telegram.updates import IntakeCommand
    from workflows.handle_intake import (
        LOW_CONFIDENCE_REPLY,
        NOT_FOOD_REPLY,
        handle_intake,
    )

    world = day._world
    tz = world.settings.timezone
    user_id = day._id("@reject")

    def command(text: str) -> IntakeCommand:
        return IntakeCommand(
            user_id=user_id,
            chat_id=world.chat_id,
            message_id=-(700_000 + len(world.tg.sent)),
            sender_label="@reject",
            display_name="Reject",
            text=text,
            surface="group",
            sent_at=datetime.now(tz),
        )

    async def low_confidence(_text: str, **_kwargs) -> FoodAnalysis:
        return FoodAnalysis(
            dish="vague heavy thali",
            calories=900,
            confidence="low",
            tip="",
            is_food=True,
        )

    async def not_food(_text: str, **_kwargs) -> FoodAnalysis:
        return FoodAnalysis(
            dish="Not food", calories=0, confidence="high", tip="", is_food=False
        )

    from core.dates import today_day_key

    for label, analyzer, expected in (
        ("low-confidence", low_confidence, LOW_CONFIDENCE_REPLY),
        ("non-food", not_food, NOT_FOOD_REPLY),
    ):
        await handle_intake(
            command("something"),
            repo=world.photo_repo,
            profile_repo=world.profile_repo,
            intake_analyzer=analyzer,
            telegram=world.tg,
            timezone=tz,
        )
        assert world.tg.sent[-1] == expected, (label, world.tg.sent[-1])

    # Nothing was stored: the rejecting user has no meals today.
    stored = await world.photo_repo.estimated_photos_for_user_day(
        chat_id=world.chat_id,
        day_key=today_day_key(tz),
        sender_label="@reject",
    )
    assert stored == [], stored
    day._say("low-confidence and non-food intakes reply with a nudge and store nothing")


async def case_rec_veg(day: Day) -> None:
    """A vegetarian no-eggs user asks for dinner; every option must fit the diet."""
    await day.profile("@aarav", "70 kg, vegetarian, no eggs, want to lose fat")
    await day.recommend("@aarav", "dinner", judge=REC_VEG)


async def case_rec_protein_gap(day: Day) -> None:
    """A carb-heavy low-protein day steers dinner protein-forward, grounded in the day."""
    await day.profile("@diya", "62 kg, want to build muscle")
    await day.seed_dish(
        "@diya", "White rice with aloo sabzi", 600, carb=110, protein=8, at_hour=9
    )
    await day.seed_dish("@diya", "Maggi noodles", 400, carb=70, protein=7, at_hour=13)
    await day.recommend("@diya", "dinner", judge=REC_PROTEIN)


async def case_rec_sugar(day: Day) -> None:
    """A high-added-sugar day gets a snack suggestion with no desserts in it."""
    await day.seed_dish(
        "@kabir", "Jalebi and sweetened chai", 450, sugar=45, at_hour=10
    )
    await day.seed_dish("@kabir", "Frooti and biscuits", 300, sugar=35, at_hour=13)
    await day.recommend("@kabir", "snack", judge=REC_NO_SWEETS)


async def case_rec_low_intake(day: Day) -> None:
    """A fat-loss user with nothing logged today is told to eat, never to restrict."""
    await day.profile("@meera", "58 kg, want to lose fat")
    await day.recommend("@meera", "dinner", judge=REC_EAT_SOMETHING)


async def case_rec_gain(day: Day) -> None:
    """A muscle-gain user gets protein-forward, adequate-calorie lunch options."""
    await day.profile("@neel", "75 kg, want to build muscle")
    await day.recommend("@neel", "lunch", judge=REC_GAIN)


async def case_rec_request(day: Day) -> None:
    """An unusual free-text ask shapes every option, not just the day's gaps."""
    await day.seed_dish(
        "@isha", "Aloo paratha with butter", 550, carb=70, protein=10, at_hour=9
    )
    await day.recommend("@isha", "food that doesn't cause oily skin", judge=REC_REQUEST)


async def case_rec_today_only(day: Day) -> None:
    """Past meals are not loaded into the recommendation context."""
    from workflows.build_recommendation_context import build_recommendation_context

    world = day._world
    await day.seed_dish("@aarav", "Dal tadka with roti and sabzi", 500, days_ago=1)
    context = await build_recommendation_context(
        user_id=day._id("@aarav"),
        sender_label="@aarav",
        surface="dm",
        slot="dinner",
        user_request="dinner",
        repo=world.photo_repo,
        profile_repo=world.profile_repo,
        chat_id=world.chat_id,
        timezone=world.settings.timezone,
    )
    assert context.today_meals == ""
    day._say("recommendation context ignores previous days")


async def case_rec_group_privacy(day: Day) -> None:
    """A group recommendation never leaks body stats, targets, or a health condition."""
    from workflows.build_recommendation_context import build_recommendation_context

    await day.profile("@aarav", "5ft9, 72 kg, 34 years old, male, want to lose fat")
    await day.context("@aarav", "I am diabetic")
    await day.seed_dish(
        "@aarav", "Poha with peanuts", 350, protein=9, carb=55, at_hour=9
    )

    # By construction (deterministic): the group-variant context never carries
    # weight-invertible numbers, even with a full profile on file.
    world = day._world
    context = await build_recommendation_context(
        user_id=day._id("@aarav"),
        sender_label="@aarav",
        surface="group",
        slot="dinner",
        user_request="dinner",
        repo=world.photo_repo,
        profile_repo=world.profile_repo,
        chat_id=world.chat_id,
        timezone=world.settings.timezone,
    )
    assert context.calorie_target is None
    assert context.remaining_kcal is None
    assert not context.dietary or "diabet" not in context.dietary.casefold()
    day._say("group context carries no raw targets or remaining budget")

    await day.recommend("@aarav", "dinner", group=True, judge=REC_GROUP_PRIVATE)


async def case_rec_buttons(day: Day) -> None:
    """A bare /recommend shows the slot keyboard; a tap sends the command and gets options (deterministic)."""
    keyboard_prompt = await day.recommend("@kabir", group=True)
    assert "Pick a meal" in keyboard_prompt, keyboard_prompt
    markup = day._world.tg.markups[-1]
    assert markup and ["/recommend dinner", "/recommend snack"] in markup["keyboard"]
    assert markup["one_time_keyboard"] and "selective" not in markup

    # Tapping a button sends its text as a normal command from the tapper.
    reply = await day.recommend("@kabir", "dinner", group=True)
    assert "What to eat next" in reply, reply


async def case_rec_fallback(day: Day) -> None:
    """Garbage LLM output falls back to safe deterministic options (deterministic)."""
    from analyzers.recommend.parser import parse_recommendations
    from domain.day import DayMacros
    from domain.recommendation import MealRecommendationContext, fallback_recommendation
    from presenters.recommend_reply import format_recommendation

    assert parse_recommendations("not even json {{{") is None
    assert parse_recommendations('{"because_today": "x", "options": []}') is None
    parsed = parse_recommendations(
        '{"request_take":"next meal","because_today":"x",'
        '"recipe_video_url":"https://youtu.be/abc","options":['
        '{"title":"Dal","calorie_range":"~300-400 kcal","why":"fits today"},'
        '{"title":"Chana","calorie_range":"~200-300 kcal","why":"fits today"}]}'
    )
    assert parsed and parsed.recipe_video_url == "https://youtu.be/abc"
    parsed = parse_recommendations(
        '{"because_today":"x","recipe_video_url":"https://example.com/recipe","options":['
        '{"title":"Dal","calorie_range":"~300-400 kcal","why":"fits today"},'
        '{"title":"Chana","calorie_range":"~200-300 kcal","why":"fits today"}]}'
    )
    assert parsed and not parsed.recipe_video_url
    context = MealRecommendationContext(
        surface="dm",
        slot="dinner",
        slot_is_explicit=True,
        user_request="",
        time_context="",
        goal=None,
        dietary="vegetarian",
        today_meals="",
        today_calories=0,
        macros=DayMacros(),
        gaps=("protein",),
    )
    result = fallback_recommendation(context)
    assert result.is_fallback and 2 <= len(result.options) <= 3
    rendered = format_recommendation(result)
    assert "What to eat next" in rendered and "None" not in rendered
    day._say("parser rejected garbage; fallback rendered safe options")


async def case_rec_label_collision(day: Day) -> None:
    """Two members sharing a display label never read each other's meals today."""
    from workflows.build_recommendation_context import build_recommendation_context

    world = day._world
    # @twin's meal belongs to the first user id; a second person with the same
    # display label must get NO current-day meals, not their namesake's meals.
    await day.seed_dish("@twin", "Dal tadka with roti", 500)
    impostor_id = world.user_id(50)
    context = await build_recommendation_context(
        user_id=impostor_id,
        sender_label="@twin",
        surface="dm",
        slot="dinner",
        user_request="dinner",
        repo=world.photo_repo,
        profile_repo=world.profile_repo,
        chat_id=world.chat_id,
        timezone=world.settings.timezone,
    )
    assert context.today_meals == ""
    day._say("same-label second member resolved to empty today, never the twin's")


CASES = {
    "profile": case_profile,
    "context": case_context,
    "image_split": case_image_split,
    "delete": case_delete,
    "day": case_day,
    "streak_reply": case_streak_reply,
    "streak_milestone": case_streak_milestone,
    "streak_grace": case_streak_grace,
    "streak_summary": case_streak_summary,
    "streak_nudge": case_streak_nudge,
    "intake": case_intake,
    "intake_routing": case_intake_routing,
    "intake_reject": case_intake_reject,
    "rec_veg": case_rec_veg,
    "rec_protein_gap": case_rec_protein_gap,
    "rec_sugar": case_rec_sugar,
    "rec_low_intake": case_rec_low_intake,
    "rec_gain": case_rec_gain,
    "rec_request": case_rec_request,
    "rec_today_only": case_rec_today_only,
    "rec_group_privacy": case_rec_group_privacy,
    "rec_buttons": case_rec_buttons,
    "rec_fallback": case_rec_fallback,
    "rec_label_collision": case_rec_label_collision,
}
