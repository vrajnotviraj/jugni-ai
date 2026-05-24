from redis.asyncio import Redis

from core.settings import Settings
from storage.photo_repository import PhotoRepository
from storage.redis_photo_repository import RedisPhotoRepository


def build_photo_repository(settings: Settings) -> PhotoRepository:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return RedisPhotoRepository(redis, timezone=settings.timezone)
