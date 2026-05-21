import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.metrics import record_rate_limit_denied

logger = get_logger(__name__)


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit middleware specifically for login and token requests."""

    def __init__(self, app: object) -> None:
        super().__init__(app)
        self.max_requests = settings.LOGIN_RATE_LIMIT_REQUESTS
        self.window = timedelta(seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        self.block_duration = timedelta(seconds=settings.LOGIN_RATE_LIMIT_BLOCK_SECONDS)
        self.login_path = f"{settings.API_V1_PREFIX}/login/access-token"
        self.requests: dict[str, deque[datetime]] = {}
        self.blocked_until: dict[str, datetime] = {}
        self.lock = asyncio.Lock()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if settings.TESTING or not settings.LOGIN_RATE_LIMIT_ENABLED:
            return await call_next(request)

        if request.url.path != self.login_path:
            return await call_next(request)

        client_ip = request.client.host if request.client else None
        forwarded_for = request.headers.get("x-forwarded-for")
        client_key = forwarded_for.split(",")[0].strip() if forwarded_for else client_ip or "unknown"

        now = datetime.now(timezone.utc)
        async with self.lock:
            blocked_until = self.blocked_until.get(client_key)
            if blocked_until and now < blocked_until:
                record_rate_limit_denied(request.url.path)
                logger.warning(
                    "login_rate_limit_blocked",
                    client_ip=client_key,
                    endpoint=request.url.path,
                )
                return JSONResponse(
                    {"detail": "Too many login attempts."},
                    status_code=429,
                    headers={"Retry-After": str(int(self.block_duration.total_seconds()))},
                )

            request_queue = self.requests.setdefault(client_key, deque())
            while request_queue and now - request_queue[0] > self.window:
                request_queue.popleft()

            if len(request_queue) >= self.max_requests:
                self.blocked_until[client_key] = now + self.block_duration
                record_rate_limit_denied(request.url.path)
                logger.warning(
                    "login_rate_limit_exceeded",
                    client_ip=client_key,
                    endpoint=request.url.path,
                    limit=self.max_requests,
                    window_seconds=self.window.total_seconds(),
                )
                return JSONResponse(
                    {"detail": "Too many login attempts."},
                    status_code=429,
                    headers={"Retry-After": str(int(self.block_duration.total_seconds()))},
                )

            request_queue.append(now)

        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(self.max_requests))
        response.headers.setdefault(
            "X-RateLimit-Remaining",
            str(max(self.max_requests - len(request_queue), 0)),
        )
        return response
