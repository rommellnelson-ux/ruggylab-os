import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.metrics import MetricsRegistry

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple IP-based rate limiter for application endpoints."""

    def __init__(self, app: object) -> None:
        super().__init__(app)
        self.max_requests = settings.RATE_LIMIT_REQUESTS
        self.window = timedelta(seconds=settings.RATE_LIMIT_WINDOW_SECONDS)
        self.block_duration = timedelta(seconds=settings.RATE_LIMIT_BLOCK_SECONDS)
        self.requests: dict[str, deque[datetime]] = {}
        self.blocked_until: dict[str, datetime] = {}
        self.lock = asyncio.Lock()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if settings.TESTING or not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        client_ip = request.client.host if request.client else None
        forwarded_for = request.headers.get("x-forwarded-for")
        client_key = forwarded_for.split(",")[0].strip() if forwarded_for else client_ip or "unknown"

        now = datetime.now(timezone.utc)
        async with self.lock:
            blocked_until = self.blocked_until.get(client_key)
            if blocked_until and now < blocked_until:
                self._record_denied(request.url.path)
                logger.warning(
                    "rate_limit_blocked",
                    client_ip=client_key,
                    endpoint=request.url.path,
                )
                return JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429,
                )

            request_queue = self.requests.setdefault(client_key, deque())
            while request_queue and now - request_queue[0] > self.window:
                request_queue.popleft()

            if len(request_queue) >= self.max_requests:
                self.blocked_until[client_key] = now + self.block_duration
                self._record_denied(request.url.path)
                logger.warning(
                    "rate_limit_exceeded",
                    client_ip=client_key,
                    endpoint=request.url.path,
                    limit=self.max_requests,
                    window_seconds=self.window.total_seconds(),
                )
                return JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429,
                )

            request_queue.append(now)

        return await call_next(request)

    def _record_denied(self, endpoint: str) -> None:
        MetricsRegistry.rate_limit_denied_total.labels(endpoint=endpoint).inc()
