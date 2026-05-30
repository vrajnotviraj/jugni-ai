import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from domain.profile import UserProfile

logger = logging.getLogger(__name__)

# Keep the most recent N context notes; older notes are trimmed on each add.
_CONTEXT_LIST_MAX = 25
# The per-user daily LLM counter self-expires after a day.
_LLM_COUNTER_TTL_SECONDS = 24 * 60 * 60

# Typed profile fields that live on the hash as plain strings. display_name is
# captured from Telegram (not LLM-extracted); the rest come from the extractor.
_WRITABLE_FIELDS = (
    "display_name",
    "height_cm",
    "weight_kg",
    "age",
    "sex",
    "activity",
    "goal",
    "diet",
    "timezone",
)


class RedisProfileRepository:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_profile(self, user_id: int) -> UserProfile | None:
        raw = await self._redis.hgetall(_profile_key(user_id))
        return _profile_from_hash(user_id, raw)

    async def update_profile_fields(
        self,
        user_id: int,
        fields: dict[str, object],
        *,
        mark_weight_updated: bool = False,
    ) -> UserProfile:
        now = datetime.now(UTC)
        mapping = _fields_to_hash(fields)
        mapping["updated_at"] = now.isoformat()

        weight = fields.get("weight_kg")
        stamping_weight = mark_weight_updated and weight is not None
        if stamping_weight:
            mapping["weight_updated_at"] = now.isoformat()

        await self._redis.hset(_profile_key(user_id), mapping=mapping)
        await self._redis.sadd(_profiles_set_key(), user_id)
        if stamping_weight:
            await self._redis.rpush(
                _weights_key(user_id), f"{now.isoformat()}|{weight}"
            )
        logger.info(
            "redis profile write user=%s fields=%s weight_appended=%s",
            user_id,
            sorted(mapping.keys()),
            stamping_weight,
        )

        profile = await self.get_profile(user_id)
        # get_profile cannot be None right after a write, but keep the type honest.
        return profile or UserProfile(user_id=user_id)

    async def weight_history(self, user_id: int) -> list[tuple[datetime, float]]:
        entries = await self._redis.lrange(_weights_key(user_id), 0, -1)
        history: list[tuple[datetime, float]] = []
        for entry in entries:
            recorded_at, _, weight = entry.partition("|")
            parsed_at = _safe_datetime(recorded_at)
            parsed_weight = _safe_float(weight)
            if parsed_at is not None and parsed_weight is not None:
                history.append((parsed_at, parsed_weight))
        return history

    async def replace_context(self, user_id: int, notes: list[str]) -> int:
        key = _context_key(user_id)
        trimmed = notes[:_CONTEXT_LIST_MAX]
        pipe = self._redis.pipeline()
        pipe.delete(key)
        if trimmed:
            pipe.rpush(key, *trimmed)
        await pipe.execute()
        logger.info("redis context replace user=%s count=%s", user_id, len(trimmed))
        return len(trimmed)

    async def list_context(self, user_id: int) -> list[str]:
        return await self._redis.lrange(_context_key(user_id), 0, -1)

    async def delete_profile(self, user_id: int) -> None:
        await self._redis.delete(
            _profile_key(user_id),
            _context_key(user_id),
            _weights_key(user_id),
        )
        await self._redis.srem(_profiles_set_key(), user_id)
        logger.info("redis profile deleted user=%s", user_id)

    async def bump_daily_llm_count(self, user_id: int, day_key: str) -> int:
        key = _llm_counter_key(user_id, day_key)
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, _LLM_COUNTER_TTL_SECONDS)
        return count

    async def close(self) -> None:
        await self._redis.aclose()


def _profile_key(user_id: int) -> str:
    return f"user:{user_id}:profile"


def _context_key(user_id: int) -> str:
    return f"user:{user_id}:context"


def _weights_key(user_id: int) -> str:
    return f"user:{user_id}:weights"


def _profiles_set_key() -> str:
    return "users:profiles"


def _llm_counter_key(user_id: int, day_key: str) -> str:
    return f"user:{user_id}:llm:{day_key}"


def _fields_to_hash(fields: dict[str, object]) -> dict[str, str]:
    return {
        key: str(fields[key])
        for key in _WRITABLE_FIELDS
        if fields.get(key) is not None
    }


def _profile_from_hash(user_id: int, raw: dict[str, str]) -> UserProfile | None:
    if not raw:
        return None
    return UserProfile(
        user_id=user_id,
        display_name=raw.get("display_name", ""),
        height_cm=_safe_int(raw.get("height_cm")),
        weight_kg=_safe_float(raw.get("weight_kg")),
        weight_updated_at=_safe_datetime(raw.get("weight_updated_at")),
        age=_safe_int(raw.get("age")),
        sex=raw.get("sex") or None,
        activity=raw.get("activity") or None,
        goal=raw.get("goal") or None,
        diet=raw.get("diet") or None,
        timezone=_safe_zone(raw.get("timezone")),
        updated_at=_safe_datetime(raw.get("updated_at")),
    )


def _safe_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _safe_zone(value: str | None) -> str | None:
    if not value:
        return None
    try:
        ZoneInfo(value)
    except Exception:
        return None
    return value
