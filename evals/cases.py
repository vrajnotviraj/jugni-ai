"""The eval scenarios — each one reads top-to-bottom as the steps it performs.

A `Day` wraps the low-level `World` with friendly, self-printing actions
(`profile`, `context`, `post`, `delete_one`, `summary`) and picks photos by type,
so a case is just a short sequence of awaits with no plumbing. A case attaches a
judging rule to any tip/summary it cares about (`judge=...`); the runner grades
them later. To add a case: write `async def case_x(day)` and list it in `CASES`.
"""

import random
import re
from pathlib import Path

from evals.harness import World

PHOTOS = Path(__file__).parent / "photos"

# Judging rules a case can attach to a tip or summary (graded pass/fail later).
# Each rule is one clear, self-contained statement so the judge cannot misread it.
TIP = "The tip is kind (not preachy) and gives a concrete suggestion that fits this specific dish, not a generic platitude."
VEG = "The tip never recommends eggs, meat, or fish as a food to eat or add (the person is vegetarian and eggless); suggesting they skip or replace such foods is fine."
SUMMARY = "The text describes one person's day with at least one strength and one gap, in plain words, and quotes no raw calorie or gram numbers."

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

    async def profile(self, user: str, text: str) -> None:
        reply = await self._world.command(
            user_id=self._id(user), text=f"/profile {text}"
        )
        self._say(f"{user} sets a profile: {text}")
        self._say("↳ " + _reply(reply))

    async def context(self, user: str, text: str) -> None:
        reply = await self._world.command(
            user_id=self._id(user), text=f"/addcontext {text}"
        )
        self._say(f"{user} adds a context note: {text}")
        self._say("↳ " + _reply(reply))

    async def post(
        self, user: str, photo: Path, *, judge: str | None = None, show: bool = True
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

    async def summary(self) -> None:
        self._say("everyone has posted; building the daily summary")
        data, text = await self._world.summary()
        print("\n" + _plain(text))
        for user in data["users"][:2]:
            if user["summary"]:
                self.to_judge.append(
                    (f"summary · {user['sender_label']}", user["summary"], SUMMARY)
                )

    def _say(self, text: str) -> None:
        self._step_no += 1
        print(f"  {self._step_no}. {text}")

    def _id(self, user: str) -> int:
        return self._ids.setdefault(user, self._world.user_id(len(self._ids)))

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


CASES = {
    "profile": case_profile,
    "context": case_context,
    "delete": case_delete,
    "day": case_day,
}
