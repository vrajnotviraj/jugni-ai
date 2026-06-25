from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from core.dates import day_key_for_datetime
from domain.analysis import FoodAnalysis
from domain.photo import DeletedMeal, Photo, PhotoStatus, StoredPhoto, UpdatedMeal
from storage._hash_codec import (
    analysis_from_hash,
    analysis_to_fields,
    failure_to_fields,
    photo_from_hash,
    photo_to_hash,
)


# TODO(timezone): meals are bucketed into a frozen, per-user local day-key
# string at write time (the Redis set keys below). That means a user's later
# timezone change does not re-bucket their history, and the same instant is
# anchored to whatever zone we knew at write time. When this moves to a SQL DB,
# store the raw instant in UTC (one canonical column) and derive the local day
# at query time from the user's current timezone, so day boundaries follow the
# profile rather than being baked into the storage key.
class RedisPhotoRepository:
    def __init__(self, redis: Redis, *, timezone: ZoneInfo) -> None:
        self._redis = redis
        self._timezone = timezone

    async def reserve(
        self,
        photo: Photo,
        *,
        day_key: str | None = None,
        content_hash: str | None = None,
    ) -> bool:
        photo_key = _photo_key(photo.chat_id, photo.message_id)
        if await self._redis.exists(photo_key):
            return False

        # The caller may pass a day_key it computed in the sender's own timezone;
        # we fall back to the app-timezone bucket only when it does not (e.g. a
        # senderless upload or a caller without profile access).
        day_key = day_key or self._day_key(photo)
        mapping = photo_to_hash(photo, day_key, content_hash=content_hash)
        mapping["reserved_at"] = datetime.now(tz=UTC).isoformat()
        await self._redis.hset(photo_key, mapping=mapping)
        await self._redis.sadd(_chat_day_key(photo.chat_id, day_key), photo.message_id)
        await self._redis.sadd(
            _user_day_key(photo.chat_id, day_key, photo.sender_label),
            photo.message_id,
        )
        return True

    async def claim_if_stale(self, photo: Photo, *, max_age_seconds: float) -> bool:
        # A PENDING reservation older than max_age is treated as abandoned — its
        # attempt was killed before reaching a terminal state. Re-stamp reserved_at
        # and return True so the caller reprocesses; a concurrent retry then sees a
        # fresh reservation and backs off, so a meal is never processed twice.
        key = _photo_key(photo.chat_id, photo.message_id)
        reserved_at = _safe_datetime(await self._redis.hget(key, "reserved_at"))
        # Pre-existing keys (reserved before this field shipped) fall back to
        # sent_at, which is old enough that they self-heal on the next retry.
        reserved_at = reserved_at or photo.sent_at
        if (datetime.now(tz=UTC) - reserved_at).total_seconds() <= max_age_seconds:
            return False
        await self._redis.hset(key, "reserved_at", datetime.now(tz=UTC).isoformat())
        return True

    async def duplicate_analysis(
        self,
        photo: Photo,
        *,
        day_key: str,
        content_hash: str | None = None,
    ) -> FoodAnalysis | None:
        if not photo.file_unique_id and not content_hash:
            return None

        message_ids = await self._redis.smembers(
            _user_day_key(photo.chat_id, day_key, photo.sender_label)
        )
        # `smembers` is unordered; walk newest-first so a match is deterministic
        # when the same image was posted more than once in the day.
        for message_id in sorted((int(m) for m in message_ids), reverse=True):
            # A webhook retry of this same message is not a deliberate re-send;
            # matching it against itself would fire a second reply for one meal.
            if message_id == photo.message_id:
                continue
            raw = await self._redis.hgetall(_photo_key(photo.chat_id, message_id))
            if _same_photo(raw, photo, content_hash):
                analysis = analysis_from_hash(raw)
                if analysis is not None:
                    return analysis
        return None

    async def complete(self, photo: Photo, analysis: FoodAnalysis) -> None:
        await self._redis.hset(
            _photo_key(photo.chat_id, photo.message_id),
            mapping=analysis_to_fields(analysis),
        )

    async def set_tip(self, photo: Photo, tip: str) -> None:
        await self._redis.hset(_photo_key(photo.chat_id, photo.message_id), "tip", tip)

    async def mark_failed(self, photo: Photo, error: str) -> None:
        await self._redis.hset(
            _photo_key(photo.chat_id, photo.message_id),
            mapping=failure_to_fields(error),
        )

    async def status(self, photo: Photo) -> PhotoStatus | None:
        raw = await self._redis.hget(
            _photo_key(photo.chat_id, photo.message_id), "status"
        )
        if raw in (None, ""):
            return None
        try:
            return PhotoStatus(raw)
        except ValueError:
            return None

    async def estimated_photos_for_day(
        self,
        *,
        chat_id: int,
        day_key: str,
    ) -> list[StoredPhoto]:
        message_ids = await self._redis.smembers(_chat_day_key(chat_id, day_key))
        ordered = sorted(int(value) for value in message_ids)
        photos: list[StoredPhoto] = []
        for mid in ordered:
            decoded = photo_from_hash(
                await self._redis.hgetall(_photo_key(chat_id, mid))
            )
            if decoded is not None:
                photos.append(decoded)
        return photos

    async def estimated_photos_for_range(
        self,
        *,
        chat_id: int,
        day_keys: list[str],
    ) -> dict[str, list[StoredPhoto]]:
        return {
            day_key: await self.estimated_photos_for_day(
                chat_id=chat_id, day_key=day_key
            )
            for day_key in day_keys
        }

    async def estimated_photos_for_user_day(
        self,
        *,
        chat_id: int,
        day_key: str,
        sender_label: str,
    ) -> list[StoredPhoto]:
        message_ids = await self._redis.smembers(
            _user_day_key(chat_id, day_key, sender_label)
        )
        photos: list[StoredPhoto] = []
        for message_id in message_ids:
            decoded = photo_from_hash(
                await self._redis.hgetall(_photo_key(chat_id, int(message_id)))
            )
            if decoded is not None:
                photos.append(decoded)
        photos.sort(key=lambda sp: sp.sent_at or datetime.min.replace(tzinfo=UTC))
        return photos

    async def user_active_days(
        self,
        *,
        chat_id: int,
        sender_label: str,
        day_keys: list[str],
    ) -> set[str]:
        if not day_keys:
            return set()
        pipe = self._redis.pipeline(transaction=False)
        for day_key in day_keys:
            pipe.exists(_user_day_key(chat_id, day_key, sender_label))
        results = await pipe.execute()
        return {
            day_key
            for day_key, present in zip(day_keys, results, strict=True)
            if present
        }

    async def daily_user_calories(
        self,
        *,
        chat_id: int,
        day_key: str,
        sender_label: str,
    ) -> int:
        message_ids = await self._redis.smembers(
            _user_day_key(chat_id, day_key, sender_label)
        )
        total = 0
        for message_id in message_ids:
            decoded = photo_from_hash(
                await self._redis.hgetall(_photo_key(chat_id, int(message_id)))
            )
            if decoded is not None:
                total += decoded.calories
        return total

    async def delete_meal(
        self,
        *,
        chat_id: int,
        message_id: int,
    ) -> DeletedMeal | None:
        photo_key = _photo_key(chat_id, message_id)
        raw = await self._redis.hgetall(photo_key)
        if not raw:
            return None

        sender_label = raw.get("sender_label", "")
        day_key = raw.get("day", "")

        if day_key:
            await self._redis.srem(_chat_day_key(chat_id, day_key), message_id)
            if sender_label:
                await self._redis.srem(
                    _user_day_key(chat_id, day_key, sender_label), message_id
                )
        await self._redis.delete(photo_key)

        return DeletedMeal(
            chat_id=chat_id,
            message_id=message_id,
            sender_label=sender_label,
            day_key=day_key,
            calories=_safe_int(raw.get("calories")),
            dish=raw.get("dish", ""),
            sent_at=_safe_datetime(raw.get("sent_at")),
        )

    async def meal_owner_id(
        self,
        *,
        chat_id: int,
        message_id: int,
    ) -> int | None:
        raw = await self._redis.hget(_photo_key(chat_id, message_id), "sender_id")
        if raw in (None, ""):
            return None
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    async def update_meal_calories(
        self,
        *,
        chat_id: int,
        message_id: int,
        calories: int,
    ) -> UpdatedMeal | None:
        photo_key = _photo_key(chat_id, message_id)
        raw = await self._redis.hgetall(photo_key)
        if not raw:
            return None

        previous = _safe_int(raw.get("calories"))
        await self._redis.hset(photo_key, "calories", calories)

        return UpdatedMeal(
            chat_id=chat_id,
            message_id=message_id,
            sender_label=raw.get("sender_label", ""),
            day_key=raw.get("day", ""),
            dish=raw.get("dish", ""),
            calories=calories,
            previous_calories=previous,
        )

    async def close(self) -> None:
        await self._redis.aclose()

    def _day_key(self, photo: Photo) -> str:
        return day_key_for_datetime(photo.sent_at, self._timezone)


def _photo_key(chat_id: int, message_id: int) -> str:
    return f"photo:{chat_id}:{message_id}"


def _chat_day_key(chat_id: int, day_key: str) -> str:
    return f"chat:{chat_id}:day:{day_key}:messages"


def _user_day_key(chat_id: int, day_key: str, sender_label: str) -> str:
    return f"chat:{chat_id}:day:{day_key}:user:{sender_label}:messages"


def _same_photo(
    raw: dict[str, object],
    photo: Photo,
    content_hash: str | None,
) -> bool:
    if photo.file_unique_id and raw.get("file_unique_id") == photo.file_unique_id:
        return True
    return bool(content_hash and raw.get("content_hash") == content_hash)


def _safe_int(value: object) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _safe_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
