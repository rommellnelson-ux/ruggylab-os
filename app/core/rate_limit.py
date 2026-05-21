import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.metrics import MetricsRegistry
from app.utils.net_utils import get_client_ip
from app.utils.redis_rate_limiter import (
    get_redis_client,
    is_blocked,
    set_block,
    sliding_window_check,
)

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiter.

    Uses Redis (sliding-window ZSET) when a Redis client is available, so
    limits are shared across all Uvicorn workers and survive restarts.
    Falls back to an in-process deque when Redis is not configured.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.max_requests = settings.RATE_LIMIT_REQUESTS
        self.window = timedelta(seconds=settings.RATE_LIMIT_WINDOW_SECONDS)
        self.block_duration = timedelta(seconds=settings.RATE_LIMIT_BLOCK_SECONDS)
        # In-memory fallback structures
        self._requests: dict[str, deque[datetime]] = {}
        self._blocked_until: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if settings.TESTING or not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        client_key = get_client_ip(request)
        redis = get_redis_client()

        if redis is not None:
            return await self._dispatch_redis(request, call_next, client_key, redis)
        return await self._dispatch_memory(request, call_next, client_key)

    # ------------------------------------------------------------------
    # Redis path
    # ------------------------------------------------------------------

    async def _dispatch_redis(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        client_key: str,
        redis: object,
    ) -> Response:
        block_key = f"rl:block:{client_key}"
        window_key = f"rl:window:{client_key}"

        try:
            if await is_blocked(redis, block_key):  # type: ignore[arg-type]
                self._record_denied(request.url.path)
                logger.warning("rate_limit_blocked_redis", client_ip=client_key)
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

            allowed, _ = await sliding_window_check(
                redis,  # type: ignore[arg-type]
                window_key,
                self.max_requests,
                self.window.total_seconds(),
            )
            if not allowed:
                await set_block(redis, block_key, int(self.block_duration.total_seconds()))  # type: ignore[arg-type]
                self._record_denied(request.url.path)
                logger.warning(
                    "rate_limit_exceeded_redis",
                    client_ip=client_key,
                    limit=self.max_requests,
                )
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        except Exception as exc:  # pragma: no cover — Redis unavailable at runtime
            logger.warning("Redis rate-limit check failed, falling back: %s", exc)
            return await self._dispatch_memory(request, call_next, client_key)

        return await call_next(request)

    # ------------------------------------------------------------------
    # In-memory fallback path
    # ------------------------------------------------------------------

    async def _dispatch_memory(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        client_key: str,
    ) -> Response:
        now = datetime.now(UTC)
        async with self._lock:
            blocked_until = self._blocked_until.get(client_key)
            if blocked_until and now < blocked_until:
                self._record_denied(request.url.path)
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

            queue = self._requests.setdefault(client_key, deque())
            while queue and now - queue[0] > self.window:
                queue.popleft()

            if len(queue) >= self.max_requests:
                self._blocked_until[client_key] = now + self.block_duration
                self._record_denied(request.url.path)
                logger.warning(
                    "rate_limit_exceeded_memory",
                    client_ip=client_key,
                    limit=self.max_requests,
                )
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

            queue.append(now)

        return await call_next(request)

    def _record_denied(self, endpoint: str) -> None:
        MetricsRegistry.rate_limit_denied_total.labels(endpoint=endpoint).inc()
