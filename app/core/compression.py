import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to compress responses using gzip.

    Only compresses responses larger than the configured minimum size.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not settings.COMPRESSION_ENABLED:
            return await call_next(request)

        # Check if client accepts gzip
        accept_encoding = request.headers.get("accept-encoding", "").lower()
        if "gzip" not in accept_encoding:
            return await call_next(request)

        response = await call_next(request)

        # Only compress if response body exists and is large enough
        if not hasattr(response, "body") or response.body is None:
            return response

        original_body = response.body
        if len(original_body) < settings.COMPRESSION_MIN_SIZE_BYTES:
            return response

        # Don't compress certain content types
        content_type = response.headers.get("content-type", "")
        if any(skip in content_type for skip in ["image/", "video/", "application/octet-stream"]):
            return response

        try:
            import gzip

            compressed_body = gzip.compress(original_body, compresslevel=6)

            if len(compressed_body) < len(original_body):
                response.body = compressed_body
                response.headers["content-encoding"] = "gzip"
                response.headers["content-length"] = str(len(compressed_body))
                logger.debug(
                    "Compressed response from %d to %d bytes",
                    len(original_body),
                    len(compressed_body),
                )
            return response
        except Exception as exc:
            logger.warning("Compression failed: %s", exc)
            return response
