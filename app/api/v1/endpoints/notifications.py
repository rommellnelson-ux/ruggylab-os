"""Notifications temps-réel — feed REST (polling) + WebSocket (push périodique)."""

from __future__ import annotations

import asyncio
import contextlib

import jwt
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.api.deps import forbid_accountant
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models import Result, User, UserRole
from app.services.notification_bus import bus
from app.services.notification_hub import build_alert_snapshot
from app.services.patient_access import can_access_result
from app.services.token_revocation import is_access_token_revoked

router = APIRouter(prefix="/notifications")

# Intervalle de push WebSocket (secondes)
_WS_PUSH_INTERVAL = 15
# Nombre maximal de connexions WebSocket simultanées par utilisateur
_WS_MAX_PER_USER = 5
# Compteur en mémoire des connexions actives par username
_ws_connections: dict[str, int] = {}


@router.get("/feed")
def notifications_feed(
    expiry_days: int = Query(default=7, ge=0, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
) -> dict:
    """Instantané des alertes actives (valeurs critiques, delta, péremptions, QC).

    Pensé pour un polling léger côté cockpit ; sert aussi de fallback au WebSocket.
    """
    return build_alert_snapshot(db, expiry_days=expiry_days, user=current_user)


def _extract_ws_token(websocket: WebSocket, query_token: str | None) -> tuple[str | None, bool]:
    """Extrait le jeton du sous-protocole WebSocket (préféré) ou du query-string.

    Convention sous-protocole : le client se connecte avec
    ``["bearer", "<jeton>"]``. L'en-tête reçu est alors ``"bearer, <jeton>"``.
    Le jeton dans l'en-tête n'apparaît pas dans les logs d'URL.

    Retourne ``(token, via_subprotocol)``.
    """
    raw = websocket.headers.get("sec-websocket-protocol")
    if raw:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) >= 2 and parts[0] == "bearer":
            return parts[1], True
    return query_token, False


def _authenticate_ws_token(token: str | None) -> tuple[str | None, str | None]:
    """Valide un JWT WebSocket. Retourne ``(username, jti)`` ou ``(None, None)``."""
    if not token:
        return None, None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except InvalidTokenError:
        return None, None
    return payload.get("sub"), payload.get("jti")


def _load_ws_user(username: str, jti: str | None) -> tuple[User | None, int | None]:
    """Recharge les droits courants sans conserver de session pendant un ``await``."""
    db = SessionLocal()
    try:
        if is_access_token_revoked(jti, db):
            return None, 4401
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active or user.role == UserRole.ACCOUNTANT:
            return None, 4403
        db.expunge(user)
        return user, None
    finally:
        db.close()


def _can_send_ws_event(user: User, event: dict) -> bool:
    """Vérifie qu'un événement lié à un résultat appartient au périmètre courant."""
    result_id = event.get("result_id")
    if result_id is None:
        return True
    db = SessionLocal()
    try:
        result = db.query(Result).filter(Result.id == result_id).first()
        return result is not None and can_access_result(user, result)
    finally:
        db.close()


@router.websocket("/ws")
async def notifications_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Pousse l'instantané des alertes à la connexion puis toutes les ~15 s.

    Authentification par jeton JWT : de préférence via le sous-protocole
    WebSocket (``Sec-WebSocket-Protocol: bearer, <jeton>``) pour éviter de
    journaliser le jeton dans les URL ; repli sur ``?token=...``.
    Un jeton révoqué (déconnexion) est refusé.
    """
    ws_token, via_subprotocol = _extract_ws_token(websocket, token)
    username, jti = _authenticate_ws_token(ws_token)
    if not username:
        await websocket.close(code=4401)  # 4401 = non authentifié (convention applicative)
        return

    # Vérifie l'utilisateur, son rôle et la denylist du jeton d'accès.
    user, rejection_code = _load_ws_user(username, jti)
    if user is None:
        await websocket.close(code=rejection_code or 4403)
        return

    # Limite anti-DoS : nombre de connexions simultanées par utilisateur
    if _ws_connections.get(username, 0) >= _WS_MAX_PER_USER:
        await websocket.close(code=4429)  # 4429 = trop de connexions
        return

    # Echo du sous-protocole négocié (requis par le protocole WebSocket si le
    # client en a proposé un), sinon accept simple.
    if via_subprotocol:
        await websocket.accept(subprotocol="bearer")
    else:
        await websocket.accept()
    _ws_connections[username] = _ws_connections.get(username, 0) + 1
    queue = bus.subscribe()

    def _snapshot(current_user: User) -> dict:
        db = SessionLocal()
        try:
            return build_alert_snapshot(db, user=current_user)
        finally:
            db.close()

    try:
        # Instantané initial
        await websocket.send_json(_snapshot(user))
        while True:
            # Attend un événement (push immédiat) OU le heartbeat (keepalive)
            event: dict | None = None
            with contextlib.suppress(TimeoutError):
                event = await asyncio.wait_for(queue.get(), timeout=_WS_PUSH_INTERVAL)

            # Un logout, une désactivation ou un changement de rôle/unité doit
            # prendre effet sur une connexion déjà ouverte.
            user, rejection_code = _load_ws_user(username, jti)
            if user is None:
                await websocket.close(code=rejection_code or 4403)
                return

            if (
                event
                and event.get("type") == "critical_value_alert"
                and _can_send_ws_event(user, event)
            ):
                await websocket.send_json(event)
            await websocket.send_json(_snapshot(user))
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 — toute erreur ferme proprement la connexion
        with contextlib.suppress(Exception):
            await websocket.close()
    finally:
        bus.unsubscribe(queue)
        remaining = _ws_connections.get(username, 1) - 1
        if remaining > 0:
            _ws_connections[username] = remaining
        else:
            _ws_connections.pop(username, None)
