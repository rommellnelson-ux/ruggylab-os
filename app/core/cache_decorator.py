import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import Request

from app.core.caching import get_cache, get_cache_key
from app.core.config import settings

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def cached(
    ttl: int | None = None,
    key_parts: list[str] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to cache endpoint responses.

    Args:
        ttl: Time to live in seconds. If None, uses default.
        key_parts: List of request attributes to include in cache key.
                   Default: ["path", "method"]
    """

    if ttl is None:
        ttl = settings.CACHE_DEFAULT_TTL_SECONDS

    if key_parts is None:
        key_parts = ["path", "method"]

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, request: Request | None = None, **kwargs: Any):
            if not settings.CACHE_ENABLED or not request:
                return await func(*args, request=request, **kwargs)

            # Skip caching for non-GET requests
            if request.method != "GET":
                return await func(*args, request=request, **kwargs)

            # Build cache key from request attributes and params
            cache_key_parts = []
            for part in key_parts:
                if part == "path":
                    cache_key_parts.append(request.url.path)
                elif part == "method":
                    cache_key_parts.append(request.method)
                elif part == "query":
                    cache_key_parts.append(str(request.query_params))
                elif part == "user_id":
                    user_id = getattr(request.state, "user_id", None)
                    if user_id:
                        cache_key_parts.append(str(user_id))

            if not cache_key_parts:
                cache_key_parts = [request.url.path]

            cache_key = get_cache_key(*cache_key_parts)
            cache = get_cache()

            # Try to get from cache
            cached_response = await cache.get(cache_key)
            if cached_response:
                logger.debug("Returning cached response for key: %s", cache_key)
                return cached_response

            # Call the actual endpoint
            response = await func(*args, request=request, **kwargs)

            # Cache the response if it's successful
            if isinstance(response, dict):
                await cache.set(cache_key, response, ttl)
                logger.debug("Cached response for key: %s (ttl: %d)", cache_key, ttl)

            return response

        return wrapper  # type: ignore

    return decorator
