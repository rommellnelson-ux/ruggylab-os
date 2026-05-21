"""
Middleware for observability: logging, metrics, and tracing.
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_config import get_logger
from app.core.metrics import record_error, record_request_metrics

logger = get_logger(__name__)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for logging, metrics, and tracing of HTTP requests."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:  # type: ignore
        """Process request and response with observability."""
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Log request start
        logger.info(
            "request_start",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        # Time the request
        start_time = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Record metrics
            record_request_metrics(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
                duration=duration,
            )

            # Log response
            logger.info(
                "request_end",
                request_id=request_id,
                status_code=response.status_code,
                duration_ms=duration * 1000,
                method=request.method,
                path=request.url.path,
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response  # type: ignore[no-any-return]

        except Exception as exc:
            duration = time.time() - start_time

            # Log error
            logger.exception(
                "request_error",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=duration * 1000,
            )

            # Record error metric
            record_error(
                error_type=type(exc).__name__,
                endpoint=request.url.path,
            )

            raise


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:  # type: ignore
        """Add request ID if not already present."""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response  # type: ignore[no-any-return]
