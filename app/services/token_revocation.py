"""Révocation des jetons d'accès (JWT) via une denylist par ``jti``.

Les jetons d'accès sont sans état ; pour les invalider avant expiration on
enregistre leur ``jti`` dans la table ``revoked_tokens``. Tout jeton dont le
``jti`` y figure (et non encore expiré) est rejeté.
"""
from __future__ import annotations

import datetime as dt

import jwt
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import RevokedToken
from app.utils.datetime_utils import utcnow_naive


def is_access_token_revoked(jti: str | None, db: Session) -> bool:
    """Retourne True si ``jti`` est dans la denylist et non expiré."""
    if not jti:
        return False
    entry = (
        db.query(RevokedToken)
        .filter(RevokedToken.jti == jti, RevokedToken.expires_at > utcnow_naive())
        .first()
    )
    return entry is not None


def revoke_access_token(token: str, db: Session, *, user_id: int | None = None) -> bool:
    """Ajoute le ``jti`` d'un jeton d'accès à la denylist.

    Décode le jeton (en ignorant l'expiration : un jeton déjà expiré n'a pas
    besoin d'être révoqué). Idempotent : ne réinsère pas un ``jti`` déjà présent.
    Retourne True si une révocation a été enregistrée.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except InvalidTokenError:
        return False

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return False

    expires_at = dt.datetime.fromtimestamp(exp, dt.UTC).replace(tzinfo=None)
    # Jeton déjà expiré → inutile de le mémoriser
    if expires_at <= utcnow_naive():
        return False

    if db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
        return False  # déjà révoqué

    db.add(
        RevokedToken(
            jti=jti,
            user_id=user_id if user_id is not None else payload.get("uid"),
            expires_at=expires_at,
        )
    )
    return True


def purge_expired_revocations(db: Session) -> int:
    """Supprime les entrées de denylist expirées. Retourne le nombre supprimé."""
    deleted = (
        db.query(RevokedToken)
        .filter(RevokedToken.expires_at <= utcnow_naive())
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)
