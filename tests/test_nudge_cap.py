import asyncio
from zoneinfo import ZoneInfo

import pytest
from redis.asyncio import Redis

from domain.streak import AtRiskUser
from presenters.streak_nudge import format_streak_nudge
from storage.redis_photo_repository import RedisPhotoRepository

# Scratch db so the test never touches the bot's data in db 0.
REDIS_URL = "redis://localhost:6379/15"


def test_nudge_run_counts_consecutive_days_and_resets_after_gap():
    async def scenario() -> list[int]:
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await redis.ping()
        except Exception:
            pytest.skip("local Redis not available")
        repo = RedisPhotoRepository(redis, timezone=ZoneInfo("UTC"))
        await redis.delete("chat:-1:user:@t:nudge")

        async def bump(day: str) -> int:
            return await repo.bump_nudge_run(chat_id=-1, sender_label="@t", day_key=day)

        runs = [
            await bump("2026-11-01"),
            await bump("2026-11-02"),
            await bump("2026-11-02"),  # cron retry on the same day
            await bump("2026-11-03"),
            await bump("2026-11-04"),  # past the cap: still counted
            await bump("2026-11-06"),  # a day with no reminder due resets
        ]
        await redis.delete("chat:-1:user:@t:nudge")
        await redis.aclose()
        return runs

    assert asyncio.run(scenario()) == [1, 2, 2, 3, 4, 1]


def test_last_reminder_says_it_stops():
    text = format_streak_nudge(
        [AtRiskUser("@a", 5), AtRiskUser("@b", 4, last_reminder=True)]
    )
    assert "🔥 @a · 5 days" in text
    assert "last reminder for @b" in text and "@a" not in text.split("🔕")[1]
