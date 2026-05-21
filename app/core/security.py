import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return cast(bool, pwd_context.verify(plain_password, hashed_password))


def get_password_hash(password: str) -> str:
    return cast(str, pwd_context.hash(password))


def create_access_token(
    subject: str, expires_delta: timedelta | None = None, scopes: list[str] | None = None
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict = {"sub": subject, "exp": expire}
    if scopes:
        to_encode["scopes"] = scopes
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token() -> str:
    """Generate a cryptographically random opaque refresh token (URL-safe)."""
    return secrets.token_urlsafe(48)


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex-digest of a raw token for safe DB storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
