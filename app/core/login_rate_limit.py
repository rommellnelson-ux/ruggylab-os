import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.metrics import record_rate_limit_denied
from app.utils.net_utils import get_client_ip
from app.utils.redis_rate_limiter import (
    get_redis_client,
    is_blocked,
    set_block,
    sliding_window_check,
)

logger = get_logger(__name__)

_DENY_RESPONSE = {"detail": "Too many login attempts."}


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    """Brute-force protection for the login endpoint.

    Uses Redis (sliding-window ZSET) when available so that limits persist
    across worker restarts and are shared across multiple processes.
    Falls back to an in-process deque when Redis is not configured.
    """

    def __init__(self, app: object) -> None:
        super().__init__(app)
        self.max_requests = settings.LOGIN_RATE_LIMIT_REQUESTS
        self.window = timedelta(seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        self.block_duration = timedelta(seconds=settings.LOGIN_RATE_LIMIT_BLOCK_SECONDS)
        self.login_path = f"{settings.API_V1_PREFIX}/login/access-token"
        # In-memory fallback
        self._requests: dict[str, deque[datetime]] = {}
        self._blocked_until: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if settings.TESTING or not settings.LOGIN_RATE_LIMIT_ENABLED:
            return await call_next(request)

        if request.url.path != self.login_path:
            return await call_next(request)

        client_key = get_client_ip(request)
        retry_after = str(int(self.block_duration.total_seconds()))
        redis = get_redis_client()

        if redis is not None:
            return await self._dispatch_redis(request, call_next, client_key, retry_after, redis)
        return await self._dispatch_memory(request, call_next, client_key, retry_after)

    # ------------------------------------------------------------------
    # Redis path
    # ------------------------------------------------------------------

    async def _dispatch_redis(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        client_key: str,
        retry_after: str,
        redis: object,
    ) -> Response:
        block_key = f"login:block:{client_key}"
        window_key = f"login:window:{client_key}"

        try:
            if await is_blocked(redis, block_key):  # type: ignore[arg-type]
                record_rate_limit_denied(request.url.path)
                logger.warning("login_rate_limit_blocked_redis", client_ip=client_key)
                return JSONResponse(
                    _DENY_RESPONSE, status_code=429, headers={"Retry-After": retry_after}
                )

            allowed, _ = await sliding_window_check(  # type: ignore[arg-type]
                redis,  # type: ignore[arg-type]
                window_key,
                self.max_requests,
                self.window.total_seconds(),
            )
            if not allowed:
                await set_block(redis, block_key, int(self.block_duration.total_seconds()))  # type: ignore[arg-type]
                record_rate_limit_denied(request.url.path)
                logger.warning(
                    "login_rate_limit_exceeded_redis",
                    client_ip=client_key,
                    limit=self.max_requests,
                )
                return JSONResponse(
                    _DENY_RESPONSE, status_code=429, headers={"Retry-After": retry_after}
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Redis login rate-limit check failed, falling back: %s", exc)
            return await self._dispatch_memory(request, call_next, client_key, retry_after)

        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(self.max_requests))
        return response

    # ------------------------------------------------------------------
    # In-memory fallback path
    # ------------------------------------------------------------------

    async def _dispatch_memory(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        client_key: str,
        retry_after: str,
    ) -> Response:
        now = datetime.now(UTC)
        async with self._lock:
            blocked_until = self._blocked_until.get(client_key)
            if blocked_until and now < blocked_until:
                record_rate_limit_denied(request.url.path)
                return JSONResponse(
                    _DENY_RESPONSE, status_code=429, headers={"Retry-After": retry_after}
                )

            queue = self._requests.setdefault(client_key, deque())
            while queue and now - queue[0] > self.window:
                queue.popleft()

            if len(queue) >= self.max_requests:
                self._blocked_until[client_key] = now + self.block_duration
                record_rate_limit_denied(request.url.path)
                logger.warning(
                    "login_rate_limit_exceeded_memory",
                    client_ip=client_key,
                    limit=self.max_requests,
                )
                return JSONResponse(
                    _DENY_RESPONSE, status_code=429, headers={"Retry-After": retry_after}
                )

            queue.append(now)

        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(self.max_requests))
        response.headers.setdefault(
            "X-RateLimit-Remaining",
            str(max(self.max_requests - len(queue), 0)),
        )
        return response
