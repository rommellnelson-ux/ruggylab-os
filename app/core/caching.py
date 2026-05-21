import hashlib
import logging
from typing import Any, TypeVar

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheBackend:
    """Abstract cache backend interface."""

    async def get(self, key: str) -> Any:
        raise NotImplementedError

    async def set(self, key: str, value: Any, ttl: int) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def clear(self) -> None:
        raise NotImplementedError


class MemoryCache(CacheBackend):
    """Simple in-memory cache backend."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> Any:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            import time

            if time.time() < expiry:
                logger.debug("Cache hit for key: %s", key)
                return value
            else:
                del self._cache[key]
                logger.debug("Cache expired for key: %s", key)
        logger.debug("Cache miss for key: %s", key)
        return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        import time

        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
        logger.debug("Cache set for key: %s (ttl: %d)", key, ttl)

    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        if key in self._cache:
            del self._cache[key]
            logger.debug("Cache delete for key: %s", key)

    async def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
        logger.debug("Cache cleared")


class RedisCache(CacheBackend):
    """Redis cache backend."""

    def __init__(self, redis_url: str | None) -> None:
        self.redis_url = redis_url or "redis://localhost:6379/0"
        self._client = None

    async def _get_client(self):
        """Lazy load Redis client."""
        if self._client is None:
            import aioredis

            self._client = await aioredis.from_url(self.redis_url)
        return self._client

    async def get(self, key: str) -> Any:
        """Get value from Redis."""
        try:
            client = await self._get_client()
            value = await client.get(key)
            if value:
                import json

                logger.debug("Cache hit for key: %s", key)
                return json.loads(value)
            logger.debug("Cache miss for key: %s", key)
            return None
        except Exception as exc:
            logger.warning("Redis get failed for key %s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in Redis with TTL."""
        try:
            import json

            client = await self._get_client()
            serialized = json.dumps(value)
            await client.setex(key, ttl, serialized)
            logger.debug("Cache set for key: %s (ttl: %d)", key, ttl)
        except Exception as exc:
            logger.warning("Redis set failed for key %s: %s", key, exc)

    async def delete(self, key: str) -> None:
        """Delete value from Redis."""
        try:
            client = await self._get_client()
            await client.delete(key)
            logger.debug("Cache delete for key: %s", key)
        except Exception as exc:
            logger.warning("Redis delete failed for key %s: %s", key, exc)

    async def clear(self) -> None:
        """Clear all cache."""
        try:
            client = await self._get_client()
            await client.flushdb()
            logger.debug("Cache cleared")
        except Exception as exc:
            logger.warning("Redis clear failed: %s", exc)


# Global cache instance
_cache_instance: CacheBackend | None = None


def init_cache() -> CacheBackend:
    """Initialize cache backend based on settings."""
    global _cache_instance

    if not settings.CACHE_ENABLED:
        logger.info("Caching disabled")
        return MemoryCache()  # Return dummy cache

    if settings.CACHE_BACKEND == "redis" and settings.REDIS_URL:
        logger.info("Initializing Redis cache backend")
        _cache_instance = RedisCache(settings.REDIS_URL)
    else:
        logger.info("Initializing in-memory cache backend")
        _cache_instance = MemoryCache()

    return _cache_instance


def get_cache() -> CacheBackend:
    """Get or initialize cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = init_cache()
    return _cache_instance


def get_cache_key(*parts: str) -> str:
    """Generate cache key from parts."""
    key_str = ":".join(parts)
    return hashlib.sha256(key_str.encode()).hexdigest()
