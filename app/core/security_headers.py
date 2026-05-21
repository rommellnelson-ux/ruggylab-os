from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds standard HTTP security headers to every response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response: Response = await call_next(request)

        if not settings.SECURITY_HEADERS_ENABLED:
            return response

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", settings.FRAME_OPTIONS)
        response.headers.setdefault("Referrer-Policy", settings.REFERRER_POLICY)
        response.headers.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)

        if settings.HSTS_ENABLED:
            hsts_value = (
                f"max-age={settings.HSTS_MAX_AGE_SECONDS};"
                f" includeSubDomains={str(settings.HSTS_INCLUDE_SUBDOMAINS).lower()};"
                f" preload={str(settings.HSTS_PRELOAD).lower()}"
            )
            response.headers.setdefault("Strict-Transport-Security", hsts_value)

        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        return response
