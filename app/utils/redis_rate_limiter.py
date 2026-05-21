"""Redis-backed sliding-window rate limiter for RuggyLab OS.

When REDIS_URL is configured the rate limiters use Redis ZSETs so that
limits are shared across multiple Uvicorn workers and survive restarts.
When Redis is unavailable the callers fall back to their own in-process
deques (the previous behaviour).

Algorithm: sliding-window using a sorted set keyed on client IP.
  ZREMRANGEBYSCORE  — evict entries older than the window
  ZCARD             — count remaining entries
  ZADD              — record current request timestamp (score = wall time)
  EXPIRE            — auto-clean keys that are no longer active

All commands are issued in a single pipeline for atomicity and latency.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Module-level client, initialised once by init_redis_client()
_redis_client: aioredis.Redis | None = None


def init_redis_client(redis_url: str) -> None:
    """Create and store the global async Redis client.

    Called once during application startup when REDIS_URL is configured.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _redis_client
    if _redis_client is not None:
        return
    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(redis_url, decode_responses=True)
        logger.info("Redis rate-limiter client initialised (%s)", redis_url)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to init Redis rate-limiter client: %s", exc)


def get_redis_client() -> aioredis.Redis | None:
    """Return the shared Redis client, or None if not initialised."""
    return _redis_client


async def sliding_window_check(
    client: aioredis.Redis,
    key: str,
    max_requests: int,
    window_seconds: float,
) -> tuple[bool, int]:
    """Atomically check and record a request in the sliding window.

    Returns:
        (allowed, current_count) where *allowed* is True when the request
        should be permitted (count was strictly below limit before recording).
    """
    now = time.time()
    window_start = now - window_seconds
    # TTL slightly longer than the window so the key self-cleans
    expire_seconds = int(window_seconds) + 10

    pipe = client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)   # evict old timestamps
    pipe.zcard(key)                                # count after eviction
    pipe.zadd(key, {str(now): now})               # record this request
    pipe.expire(key, expire_seconds)              # auto-expire key
    results = await pipe.execute()

    count_before: int = results[1]
    allowed = count_before < max_requests
    return allowed, count_before


async def is_blocked(client: aioredis.Redis, block_key: str) -> bool:
    """Return True when a block key exists in Redis (TTL still active)."""
    return bool(await client.exists(block_key))


async def set_block(
    client: aioredis.Redis,
    block_key: str,
    block_seconds: int,
) -> None:
    """Set a block flag that expires after *block_seconds*."""
    await client.setex(block_key, block_seconds, "1")
