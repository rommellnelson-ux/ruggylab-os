"""Notifications temps-réel — feed REST (polling) + WebSocket (push périodique)."""
from __future__ import annotations

import asyncio

import jwt
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models import User
from app.services.notification_hub import build_alert_snapshot

router = APIRouter(prefix="/notifications")

# Intervalle de push WebSocket (secondes)
_WS_PUSH_INTERVAL = 15


@router.get("/feed")
def notifications_feed(
    expiry_days: int = Query(default=7, ge=0, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Instantané des alertes actives (valeurs critiques, delta, péremptions, QC).

    Pensé pour un polling léger côté cockpit ; sert aussi de fallback au WebSocket.
    """
    del current_user
    return build_alert_snapshot(db, expiry_days=expiry_days)


def _authenticate_ws_token(token: str | None) -> str | None:
    """Valide un JWT passé en query-string. Retourne le username ou None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except InvalidTokenError:
        return None
    return payload.get("sub")


@router.websocket("/ws")
async def notifications_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Pousse l'instantané des alertes à la connexion puis toutes les ~15 s.

    Authentification par jeton JWT en query-string (``?token=...``) car les
    en-têtes Authorization ne sont pas exploitables côté navigateur pour les WS.
    """
    username = _authenticate_ws_token(token)
    if not username:
        await websocket.close(code=4401)  # 4401 = non authentifié (convention applicative)
        return

    # Vérifie que l'utilisateur existe et est actif
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            await websocket.close(code=4403)  # 4403 = interdit
            return
    finally:
        db.close()

    await websocket.accept()
    try:
        while True:
            db = SessionLocal()
            try:
                snapshot = build_alert_snapshot(db)
            finally:
                db.close()
            await websocket.send_json(snapshot)
            await asyncio.sleep(_WS_PUSH_INTERVAL)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 — toute erreur ferme proprement la connexion
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
