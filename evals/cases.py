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

from evals.harness import World

PHOTOS = Path(__file__).parent / "photos"

# Judging rules a case can attach to a tip or summary (graded pass/fail later).
# Each rule is one clear, self-contained statement so the judge cannot misread it.
TIP = "The tip is kind (not preachy) and gives a concrete suggestion that fits this specific dish, not a generic platitude."
VEG = "The tip never recommends eggs, meat, or fish as a food to eat or add (the person is vegetarian and eggless); suggesting they skip or replace such foods is fine."
SUMMARY = "The text describes one person's day with at least one strength and one gap, in plain words, and quotes no raw calorie or gram numbers."

# Streak rules. The reply rules embed the exact day-count the seeded history
# must produce, so the judge verifies the streak maths, not just the wording.
STREAK_5 = "The text tells the user they are on a 5-day streak (it states the number 5 as the streak/day count) and encourages them to keep it going."
STREAK_MILESTONE = "The text celebrates a 7-day streak as a milestone with congratulatory wording (e.g. a 'week' achievement), not just a plain count."
STREAK_GRACE = "The text tells the user they are on a 4-day streak (it states the number 4 as the day count) and encourages them to keep going."
NO_STREAK = "The text is a normal meal reply and does NOT mention any streak, consecutive-day count, or 'don't break the chain' language."
SUMMARY_STREAK = "The leaderboard text shows a consecutive-day streak count (a number of days running) for at least one person, alongside their meal stats."
NUDGE_KIND = "The message asks people to log a meal before the day ends to keep their streak alive, in an encouraging, non-shaming tone (no blame or 'you failed' wording)."

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
            await self._world.seed_meal(
                label=user, user_id=self._id(user), when=when
            )
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
        if show:
            self._say(
                f"{user} posts at {when}: {analysis['dish']} · {analysis['calories']} kcal"
            )
            print(f"        tip: {analysis['tip']}")
        if judge:
            self.to_judge.append((f"tip · {analysis['dish']}", analysis["tip"], judge))
        if judge_reply:
            reply = _plain(result.get("reply_text", ""))
            self.to_judge.append((f"reply · {analysis['dish']}", reply, judge_reply))

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


CASES = {
    "profile": case_profile,
    "context": case_context,
    "delete": case_delete,
    "day": case_day,
    "streak_reply": case_streak_reply,
    "streak_milestone": case_streak_milestone,
    "streak_grace": case_streak_grace,
    "streak_summary": case_streak_summary,
    "streak_nudge": case_streak_nudge,
}
