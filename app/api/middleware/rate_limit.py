"""Rate limiting middleware for API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.utils.datetime_utils import utcnow_naive


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Basic in-memory rate limiter: 100 requests per user per minute."""

    def __init__(self, app: ASGIApp, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._requests: dict[str, list[datetime]] = {}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Identify user by token or IP
        user_id = self._get_user_id(request)
        now = utcnow_naive()
        cutoff = now - timedelta(minutes=1)

        if user_id not in self._requests:
            self._requests[user_id] = []

        # Prune old requests
        self._requests[user_id] = [t for t in self._requests[user_id] if t > cutoff]

        # Check rate limit
        if len(self._requests[user_id]) >= self.requests_per_minute:
            return Response("Rate limit exceeded", status_code=429)

        # Record request
        self._requests[user_id].append(now)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            self.requests_per_minute - len(self._requests[user_id])
        )
        return response

    def _get_user_id(self, request: Request) -> str:
        # Try to extract user from token
        if auth_header := request.headers.get("Authorization"):
            return auth_header.split()[-1][:16]  # Token prefix
        # Fallback to IP
        return request.client.host if request.client else "unknown"
