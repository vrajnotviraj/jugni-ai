"""One place that wires the real bot up and exposes its route handlers as methods.

The FastAPI routes are plain async functions; we build the real deps once (Redis +
OpenAI, same as api/lifespan.py) and pass them in, so a `World` method is exactly an
API call without the socket. Cases only ever touch `World`, so they import almost
nothing. Telegram is the one stand-in: it records replies instead of sending them.

Everything writes under a synthetic eval chat / user-id range and `purge()` removes
exactly those keys, so real data is never touched.
"""

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from openai import AsyncOpenAI
from redis.asyncio import Redis

from analyzers.context.rewriter import build_context_rewriter
from analyzers.image.factory import build_image_estimator
from analyzers.profile.extractor import build_profile_extractor
from analyzers.recommend.factory import build_recommender
from analyzers.summary.factory import build_day_summarizer
from api.routes.meals import delete_meal as delete_meal_route
from api.routes.meals import list_all_meals
from api.routes.profiles import SimulateCommandRequest, simulate_command
from api.routes.summary import get_day_summary
from api.routes.upload import upload_food_photo
from core.settings import Settings
from domain.analysis import FoodAnalysis
from domain.photo import Photo
from domain.streak import AtRiskUser
from presenters.streak_nudge import STREAK_NUDGE_PARSE_MODE, format_streak_nudge
from storage.redis_photo_repository import RedisPhotoRepository
from storage.redis_profile_repository import RedisProfileRepository
from workflows.dispatch_update import Dependencies, dispatch_update
from workflows.streak_nudge import build_streak_nudge

EVAL_CHAT_ID = -9_990_000_001
USER_ID_BASE = 990_000_001

# A minimal stored meal used to seed prior-day activity without an OpenAI call.
# The streak only reads day-presence, so the exact numbers don't matter.
_SEED_ANALYSIS = FoodAnalysis(
    dish="seeded meal", calories=1, confidence="high", tip="", is_food=True
)


class _Telegram:
    """Records outgoing messages instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        # The reply_markup of each sent message (None for plain messages), so
        # cases can assert on the /recommend slot keyboard.
        self.markups: list[dict | None] = []
        self._next_id = 1000

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        **_: object,
    ) -> int:
        self.sent.append(text)
        self.markups.append(reply_markup)
        self._next_id += 1
        return self._next_id

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str, **_: object
    ) -> None:
        # The placeholder→edit flow overwrites the message in place; mirror that
        # so `sent[-1]` reflects the finished card, not the "Analysing…" stub.
        index = message_id - 1001
        if 0 <= index < len(self.sent):
            self.sent[index] = text

    async def send_document(self, *_: object, **__: object) -> None:
        pass

    async def set_my_commands(self, *_: object, **__: object) -> None:
        pass


@dataclass(slots=True)
class World:
    settings: Settings
    redis: Redis
    photo_repo: RedisPhotoRepository
    profile_repo: RedisProfileRepository
    image_estimator: object
    day_summarizer: object
    deps: Dependencies
    tg: _Telegram
    openai: AsyncOpenAI
    chat_id: int = EVAL_CHAT_ID
    user_ids: set[int] = field(default_factory=set)

    def user_id(self, n: int) -> int:
        self.user_ids.add(USER_ID_BASE + n)
        return USER_ID_BASE + n

    @property
    def _secret(self) -> str | None:
        return self.settings.admin_api_secret

    async def upload(
        self, image: Path, *, label: str, user_id: int | None, time: str
    ) -> dict:
        """POST /api/upload. The filename (minus any s_/m_ prefix) is the caption."""
        stem = image.stem
        for prefix in ("s_", "m_"):
            if stem.lower().startswith(prefix):
                stem = stem[len(prefix) :]
                break
        caption = stem.replace("_", " ").strip()
        upload = UploadFile(filename=image.name, file=BytesIO(image.read_bytes()))
        before = len(self.tg.sent)
        result = await upload_food_photo(
            image=upload,
            user_label=label,
            chat_id=self.chat_id,
            caption=caption,
            user_id=user_id,
            time=time,
            settings=self.settings,
            telegram=self.tg,
            repo=self.photo_repo,
            profile_repo=self.profile_repo,
            image_estimator=self.image_estimator,
            admin_secret=self._secret,
        )
        # The streak line lands in the sent reply, not the returned analysis.
        result["reply_text"] = self.tg.sent[-1] if len(self.tg.sent) > before else ""
        return result

    async def seed_meal(
        self,
        *,
        label: str,
        user_id: int,
        when: datetime,
        analysis: FoodAnalysis | None = None,
    ) -> None:
        """Store a meal directly (no vision call) so a user reads as having
        logged on ``when``'s local day. Pass ``analysis`` to seed real dishes
        and macros (recommend cases); the default minimal seed only marks
        day-presence (streak cases). The hour keeps same-day seeds distinct."""
        message_id = -(user_id * 10_000_000 + when.date().toordinal() * 100 + when.hour)
        photo = Photo(
            update_id=0,
            chat_id=self.chat_id,
            message_id=message_id,
            sender_id=user_id,
            sender_label=label,
            sent_at=when,
            file_id=f"seed:{message_id}",
            file_unique_id=None,
            caption=None,
        )
        if await self.photo_repo.reserve(photo):
            await self.photo_repo.complete(photo, analysis or _SEED_ANALYSIS)

    async def recommend(
        self,
        *,
        user_id: int,
        text: str = "",
        username: str | None = None,
        group: bool = False,
    ) -> str:
        """Send a real /recommend update through dispatch; returns the reply.

        ``username`` must match the label meals were seeded under (minus the
        "@") or the day-meal join silently tests the empty-day path."""
        before = len(self.tg.sent)
        chat = (
            {"id": self.chat_id, "type": "supergroup"}
            if group
            else {"id": user_id, "type": "private"}
        )
        update = {
            "update_id": 0,
            "message": {
                "chat": chat,
                "from": {"id": user_id, "username": username, "first_name": "Eval"},
                "text": f"/recommend {text}".strip(),
            },
        }
        await dispatch_update(update, deps=self.deps)
        return "\n".join(self.tg.sent[before:])

    async def nudge(self) -> tuple[list[AtRiskUser], str]:
        """Run the evening at-risk check and send the one consolidated message
        (when anyone is at risk), returning the at-risk list and the sent text."""
        before = len(self.tg.sent)
        at_risk = await build_streak_nudge(
            repo=self.photo_repo, chat_id=self.chat_id, timezone=self.settings.timezone
        )
        if at_risk:
            await self.tg.send_message(
                self.chat_id,
                format_streak_nudge(at_risk),
                parse_mode=STREAK_NUDGE_PARSE_MODE,
            )
        return at_risk, "\n".join(self.tg.sent[before:])

    async def command(self, *, user_id: int, text: str) -> dict:
        """POST /api/profiles/simulate — runs a real DM command (/profile, /context)."""
        return await simulate_command(
            payload=SimulateCommandRequest(
                user_id=user_id, text=text, first_name="Eval"
            ),
            settings=self.settings,
            deps=self.deps,
            admin_secret=self._secret,
        )

    async def meals(self) -> dict:
        """GET /api/meals — stored meals grouped by user."""
        return await list_all_meals(
            date=None,
            chat_id=self.chat_id,
            settings=self.settings,
            repo=self.photo_repo,
            admin_secret=self._secret,
        )

    async def delete(self, message_id: int) -> dict:
        """DELETE /api/meals/{id} — remove a meal and recompute the total."""
        return await delete_meal_route(
            message_id=message_id,
            chat_id=self.chat_id,
            notify=False,
            settings=self.settings,
            repo=self.photo_repo,
            telegram=self.tg,
            admin_secret=self._secret,
        )

    async def summary(self) -> tuple[dict, str]:
        """GET /api/summary (send=True) — returns (data, formatted leaderboard text)."""
        before = len(self.tg.sent)
        data = await get_day_summary(
            date=None,
            chat_id=self.chat_id,
            send=True,
            settings=self.settings,
            repo=self.photo_repo,
            profile_repo=self.profile_repo,
            day_summarizer=self.day_summarizer,
            telegram=self.tg,
            admin_secret=self._secret,
        )
        return data, "\n\n".join(self.tg.sent[before:])

    async def purge(self) -> int:
        patterns = [f"photo:{self.chat_id}:*", f"chat:{self.chat_id}:*"]
        patterns += [f"user:{uid}:*" for uid in self.user_ids]
        deleted = 0
        for pattern in patterns:
            async for key in self.redis.scan_iter(match=pattern, count=200):
                deleted += await self.redis.delete(key)
        if self.user_ids:
            await self.redis.srem("users:profiles", *map(str, self.user_ids))
        return deleted

    async def aclose(self) -> None:
        await self.redis.aclose()


async def build_world() -> World:
    s = Settings.from_environment()
    redis = Redis.from_url(s.redis_url, decode_responses=True)
    # Generous retries: eval runs share the project's rate limits with the
    # live bot, so a 429 should back off and continue, not sink the case.
    openai = AsyncOpenAI(api_key=s.openai_api_key, max_retries=5)
    tg = _Telegram()
    photo_repo = RedisPhotoRepository(redis, timezone=s.timezone)
    profile_repo = RedisProfileRepository(redis)
    image_estimator = build_image_estimator(s, openai)
    day_summarizer = build_day_summarizer(s, openai)
    deps = Dependencies(
        repo=photo_repo,
        profile_repo=profile_repo,
        image_estimator=image_estimator,
        day_summarizer=day_summarizer,
        profile_extractor=build_profile_extractor(s, openai),
        context_rewriter=build_context_rewriter(s, openai),
        recommender=build_recommender(s, openai),
        telegram=tg,
        timezone=s.timezone,
        # The eval chat is the one allowed group, so group-surface dispatch
        # passes the allowlist and DM /recommend can read today's meals from it.
        allowed_chat_ids=(EVAL_CHAT_ID,),
    )
    return World(
        settings=s,
        redis=redis,
        photo_repo=photo_repo,
        profile_repo=profile_repo,
        image_estimator=image_estimator,
        day_summarizer=day_summarizer,
        deps=deps,
        tg=tg,
        openai=openai,
    )
