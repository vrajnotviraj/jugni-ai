"""Chooses which tier each OpenAI call takes, per model and recent uptime.

A *route* is how a request is sent. There are two:

  * the **flex** service tier — ~50% cheaper, but slower and capacity-limited, so
    it runs with a longer timeout (slow is fine; it's the cheap lane), and
  * the **primary** (default) tier — the reliable lane we always fall back to.

Flex is used only when (a) the call's model actually supports it — gpt-4.1 and
friends reject ``service_tier=flex`` — and (b) flex isn't currently marked down.
When a flex call times out or hits a 429, ``report_unavailable`` marks flex down
for 15 minutes; the caller then fails this attempt and the *next* call (a Telegram
webhook retry, or the image tip's own fallback) takes the primary lane. Health is
keyed in Redis so every Vercel worker shares one view — pass ``redis=None`` to keep
it in-process for evals, where a trip must never touch the key the live bot reads.

This is the single seam for routing. Adding a model, or failing over to another
provider (e.g. Anthropic when OpenAI's uptime drops), means editing here only —
the analyzers all call through ``call_responses`` and never see it.
"""

import logging
import time
from dataclasses import dataclass

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

FLEX_DOWN_KEY = "llm:flex:down"
COOLDOWN_SECONDS = 15 * 60

# Model families OpenAI offers the flex service tier on. Other models (e.g.
# gpt-4.1) reject service_tier=flex with a 400, so we never route them through it.
# Matched as id prefixes so date-stamped ids (gpt-5.4-2026-03-05) are covered.
# Extend as OpenAI widens flex availability.
FLEX_MODEL_PREFIXES = ("gpt-5", "o3", "o4-mini")


def supports_flex(model: str) -> bool:
    return model.startswith(FLEX_MODEL_PREFIXES)


@dataclass(frozen=True, slots=True)
class Route:
    """How to send one request. ``service_tier`` None means the primary tier."""

    service_tier: str | None = None
    timeout: float | None = None


PRIMARY_ROUTE = Route()


class SmartRouter:
    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._flex = PRIMARY_ROUTE
        # In-process cooldown deadline, used only when there is no shared Redis.
        self._flex_down_until = 0.0

    def configure(
        self, *, redis: Redis | None, flex_enabled: bool, flex_timeout: float
    ) -> None:
        self._redis = redis
        self._flex = Route("flex", flex_timeout) if flex_enabled else PRIMARY_ROUTE
        self._flex_down_until = 0.0
        if flex_enabled:
            logger.info(
                "smart router: flex on (timeout=%ss, models=%s*, shared_breaker=%s)",
                flex_timeout,
                "*/".join(FLEX_MODEL_PREFIXES),
                redis is not None,
            )
        else:
            logger.info("smart router: flex off; every call uses the primary tier")

    async def pick(self, model: str) -> Route:
        """The best route to try right now for ``model``."""
        if self._flex.service_tier != "flex":
            return PRIMARY_ROUTE
        if not supports_flex(model):
            logger.debug("flex skipped: model %s is not flex-capable", model)
            return PRIMARY_ROUTE
        if await self._flex_is_down():
            logger.debug("flex skipped: in cooldown")
            return PRIMARY_ROUTE
        return self._flex

    async def report_unavailable(self, route: Route) -> None:
        """Mark flex down after a flex call timed out or ran out of capacity."""
        if route.service_tier != "flex":
            return
        logger.warning(
            "flex unavailable; routing to primary tier for %ds", COOLDOWN_SECONDS
        )
        if self._redis is not None:
            await self._redis.set(FLEX_DOWN_KEY, "1", ex=COOLDOWN_SECONDS)
        else:
            self._flex_down_until = time.time() + COOLDOWN_SECONDS

    async def _flex_is_down(self) -> bool:
        if self._redis is not None:
            return bool(await self._redis.exists(FLEX_DOWN_KEY))
        return time.time() < self._flex_down_until


_router = SmartRouter()

configure_router = _router.configure
pick_route = _router.pick
report_unavailable = _router.report_unavailable
