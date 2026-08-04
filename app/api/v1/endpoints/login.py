from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.services.token_revocation import revoke_access_token
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/login")


def _issue_tokens(user: User, db: Session, scopes: list[str] | None = None) -> Token:
    """Create and persist a new access + refresh token pair for *user*."""
    access_token = create_access_token(
        user.username,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        scopes=scopes,
        auth_version=user.auth_version,
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
    user = db.query(User).filter(User.username == form_data.username).with_for_update().first()
    authenticated = bool(user and verify_password(form_data.password, user.hashed_password))
    record_auth_attempt(authenticated)

    if not authenticated or user is None:
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
    db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expire.",
        )

    # Ordre de verrouillage partagé avec les mises à jour de compte :
    # utilisateur, puis refresh token. Il sérialise la rotation avec une
    # révocation globale sans créer d'interblocage.
    user = db.query(User).filter(User.id == db_token.user_id).with_for_update().first()
    db_token = (
        db.query(RefreshToken).filter(RefreshToken.id == db_token.id).with_for_update().first()
    )

    if not db_token or not db_token.is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expire.",
        )

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
def logout(
    payload: LogoutRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    """Termine la session : révoque le refresh token ET le jeton d'accès courant.

    Le jeton d'accès est lu dans l'en-tête ``Authorization`` (s'il est présent)
    et ajouté à la denylist par ``jti`` — il devient inutilisable immédiatement,
    y compris pour les connexions WebSocket.
    """
    db_token = None
    if payload.refresh_token:
        token_hash = hash_token(payload.refresh_token)
        db_token = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .first()
        )
        if db_token:
            db_token.revoked_at = utcnow_naive()

    # Révocation immédiate du jeton d'accès (denylist par jti)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        access_token = auth_header[7:].strip()
        revoke_access_token(access_token, db, user_id=db_token.user_id if db_token else None)

    db.commit()
