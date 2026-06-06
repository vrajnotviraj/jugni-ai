from redis.asyncio import Redis

from core.settings import Settings
from storage.photo_repository import PhotoRepository
from storage.profile_repository import ProfileRepository
from storage.redis_photo_repository import RedisPhotoRepository
from storage.redis_profile_repository import RedisProfileRepository
from storage.webhook_dedupe import WebhookDedupe


def build_photo_repository(settings: Settings) -> PhotoRepository:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return RedisPhotoRepository(redis, timezone=settings.timezone)


def build_profile_repository(settings: Settings) -> ProfileRepository:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return RedisProfileRepository(redis)


def build_webhook_dedupe(settings: Settings) -> WebhookDedupe:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return WebhookDedupe(redis)
