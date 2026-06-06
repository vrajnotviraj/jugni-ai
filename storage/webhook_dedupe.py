from redis.asyncio import Redis

SENT_TTL_SECONDS = 60 * 60


class WebhookDedupe:
    """Redis-backed sent-reply marker for Telegram webhook retries."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def was_sent(self, update_id: int | None) -> bool:
        if update_id is None:
            return False
        return bool(await self._redis.get(_sent_key(update_id)))

    async def mark_sent(self, update_id: int | None) -> None:
        if update_id is None:
            return
        await self._redis.set(_sent_key(update_id), "1", ex=SENT_TTL_SECONDS)

    async def close(self) -> None:
        await self._redis.aclose()


def _sent_key(update_id: int) -> str:
    return f"telegram:update:{update_id}:sent"
