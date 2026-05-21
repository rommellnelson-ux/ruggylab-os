from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import record_auth_attempt
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_password,
)
from app.db.session import get_db
from app.models import RefreshToken, User
from app.schemas.auth import LogoutRequest, RefreshRequest, Token
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/login")


def _issue_tokens(user: User, db: Session, scopes: list[str] | None = None) -> Token:
    """Create and persist a new access + refresh token pair for *user*."""
    access_token = create_access_token(
        user.username,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        scopes=scopes,
    )
    raw_refresh = create_refresh_token()
    expires_at = utcnow_naive() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db_refresh = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=expires_at,
    )
    db.add(db_refresh)
    db.commit()
    return Token(access_token=access_token, refresh_token=raw_refresh)


@router.post("/access-token", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    user = db.query(User).filter(User.username == form_data.username).first()
    authenticated = bool(user and verify_password(form_data.password, user.hashed_password))
    record_auth_attempt(authenticated)

    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur desactive.",
        )

    return _issue_tokens(user, db, scopes=form_data.scopes)


@router.post("/refresh", response_model=Token)
def refresh_access_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> Token:
    """Exchange a valid refresh token for a new access + refresh token pair.

    The old refresh token is revoked (rotation) to limit the blast radius of
    a stolen token.
    """
    token_hash = hash_token(payload.refresh_token)
    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .with_for_update()
        .first()
    )

    if not db_token or not db_token.is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expire.",
        )

    user = db.query(User).filter(User.id == db_token.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur desactive.",
        )

    # Revoke the used token (rotation — one-time use)
    db_token.revoked_at = utcnow_naive()
    db.flush()

    return _issue_tokens(user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> None:
    """Revoke a refresh token, effectively ending the session."""
    token_hash = hash_token(payload.refresh_token)
    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .first()
    )
    if db_token:
        db_token.revoked_at = utcnow_naive()
        db.commit()
