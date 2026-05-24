from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from core.dates import day_key_for_datetime
from domain.analysis import FoodAnalysis
from domain.photo import Photo, StoredPhoto
from storage._hash_codec import (
    analysis_to_fields,
    failure_to_fields,
    photo_from_hash,
    photo_to_hash,
)


class RedisPhotoRepository:
    def __init__(self, redis: Redis, *, timezone: ZoneInfo) -> None:
        self._redis = redis
        self._timezone = timezone

    async def reserve(self, photo: Photo) -> bool:
        photo_key = _photo_key(photo.chat_id, photo.message_id)
        if await self._redis.exists(photo_key):
            return False

        day_key = self._day_key(photo)
        await self._redis.hset(photo_key, mapping=photo_to_hash(photo, day_key))
        await self._redis.sadd(_chat_day_key(photo.chat_id, day_key), photo.message_id)
        await self._redis.sadd(
            _user_day_key(photo.chat_id, day_key, photo.sender_label),
            photo.message_id,
        )
        return True

    async def complete(self, photo: Photo, analysis: FoodAnalysis) -> None:
        await self._redis.hset(
            _photo_key(photo.chat_id, photo.message_id),
            mapping=analysis_to_fields(analysis),
        )

    async def mark_failed(self, photo: Photo, error: str) -> None:
        await self._redis.hset(
            _photo_key(photo.chat_id, photo.message_id),
            mapping=failure_to_fields(error),
        )

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

    async def daily_user_total(self, photo: Photo) -> int:
        day_key = self._day_key(photo)
        message_ids = await self._redis.smembers(
            _user_day_key(photo.chat_id, day_key, photo.sender_label)
        )
        total = 0
        for message_id in message_ids:
            decoded = photo_from_hash(
                await self._redis.hgetall(_photo_key(photo.chat_id, int(message_id)))
            )
            if decoded is not None:
                total += decoded.calories
        return total

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
