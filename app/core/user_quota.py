import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class UserQuotaMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce per-user request quotas.

    Tracks authenticated user requests and blocks if quota exceeded.
    Requires user ID to be set in request.state.user_id by auth middleware.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        # In-memory storage for user request counts (use Redis in production)
        self._user_requests: dict[str, list[datetime]] = defaultdict(list)
        self._blocked_users: dict[str, datetime] = {}

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not settings.USER_QUOTA_ENABLED:
            return await call_next(request)

        # Skip quota check for health endpoints and unauthenticated requests
        if request.url.path.startswith("/health") or not hasattr(request.state, "user_id"):
            return await call_next(request)

        user_id = request.state.user_id
        now = datetime.now(UTC)

        # Check if user is currently blocked
        if user_id in self._blocked_users:
            block_until = self._blocked_users[user_id]
            if now < block_until:
                logger.warning(
                    "User %s quota exceeded, blocked until %s",
                    user_id,
                    block_until.isoformat(),
                )
                return JSONResponse(
                    {"detail": "User quota exceeded. Try again later."},
                    status_code=429,
                )
            else:
                # Block expired, remove from blocked list
                del self._blocked_users[user_id]

        # Clean old requests outside the window
        window_start = now - timedelta(seconds=settings.USER_QUOTA_WINDOW_SECONDS)
        self._user_requests[user_id] = [
            req_time for req_time in self._user_requests[user_id] if req_time > window_start
        ]

        # Check quota
        if len(self._user_requests[user_id]) >= settings.USER_QUOTA_REQUESTS:
            # Block user
            block_until = now + timedelta(seconds=settings.USER_QUOTA_BLOCK_SECONDS)
            self._blocked_users[user_id] = block_until
            logger.warning(
                "User %s exceeded quota (%d requests in %d seconds), blocked until %s",
                user_id,
                settings.USER_QUOTA_REQUESTS,
                settings.USER_QUOTA_WINDOW_SECONDS,
                block_until.isoformat(),
            )
            return JSONResponse(
                {"detail": "User quota exceeded. Try again later."},
                status_code=429,
            )

        # Record request
        self._user_requests[user_id].append(now)

        response = await call_next(request)
        return response
