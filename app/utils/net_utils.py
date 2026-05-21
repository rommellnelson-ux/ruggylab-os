"""Network utilities for RuggyLab OS.

Provides a safe client IP resolution that only trusts X-Forwarded-For
when the direct peer IP is in the configured TRUSTED_PROXY_IPS list.
This prevents IP spoofing when the server is exposed directly to the internet.
"""

from fastapi import Request

from app.core.config import settings


def get_client_ip(request: Request) -> str:
    """Return the real client IP address.

    Trust X-Forwarded-For only when the direct peer IP matches one of the
    configured TRUSTED_PROXY_IPS.  When no trusted proxy is configured (the
    default), the direct peer IP is always used, making IP forging impossible.
    """
    peer_ip: str = request.client.host if request.client else "unknown"

    if settings.TRUSTED_PROXY_IPS and peer_ip in settings.TRUSTED_PROXY_IPS:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the left-most IP (the original client), strip whitespace
            return forwarded_for.split(",")[0].strip()

    return peer_ip
