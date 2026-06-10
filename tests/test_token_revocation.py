"""Tests — Révocation des jetons d'accès (denylist jti) + déconnexion + WS."""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


def _login(client) -> dict:
    return client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAccessTokenHasJti:
    def test_token_decodes_with_jti(self, client):
        import jwt

        from app.core.config import settings

        access = _login(client)["access_token"]
        payload = jwt.decode(access, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert "jti" in payload
        assert "iat" in payload
        assert payload["sub"] == "admin"


class TestLogoutRevokesAccessToken:
    def test_token_works_before_logout(self, client):
        access = _login(client)["access_token"]
        r = client.get("/api/v1/users/me", headers=_bearer(access))
        assert r.status_code == 200

    def test_token_rejected_after_logout(self, client):
        tokens = _login(client)
        access = tokens["access_token"]
        # Déconnexion (révoque le jeton d'accès via l'en-tête Authorization)
        out = client.post(
            "/api/v1/login/logout",
            headers=_bearer(access),
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert out.status_code == 204
        # Le même jeton ne doit plus fonctionner
        r = client.get("/api/v1/users/me", headers=_bearer(access))
        assert r.status_code == 401

    def test_logout_without_refresh_token_still_revokes_access(self, client):
        access = _login(client)["access_token"]
        out = client.post("/api/v1/login/logout", headers=_bearer(access), json={})
        assert out.status_code == 204
        r = client.get("/api/v1/users/me", headers=_bearer(access))
        assert r.status_code == 401

    def test_other_token_unaffected_by_logout(self, client):
        first = _login(client)["access_token"]
        second = _login(client)["access_token"]
        client.post("/api/v1/login/logout", headers=_bearer(first), json={})
        # Le second jeton, indépendant, reste valide
        r = client.get("/api/v1/users/me", headers=_bearer(second))
        assert r.status_code == 200


class TestRevokedTokenRejectedOnWebSocket:
    def test_revoked_token_cannot_open_ws(self, client):
        tokens = _login(client)
        access = tokens["access_token"]
        client.post("/api/v1/login/logout", headers=_bearer(access), json={})
        # WS via query-string avec un jeton révoqué → refusé
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/v1/notifications/ws?token={access}") as ws:
                ws.receive_json()

    def test_valid_token_via_subprotocol(self, client):
        access = _login(client)["access_token"]
        # Authentification par sous-protocole ["bearer", <token>]
        with client.websocket_connect(
            "/api/v1/notifications/ws", subprotocols=["bearer", access]
        ) as ws:
            snap = ws.receive_json()
            assert "total" in snap
            assert "counts" in snap


class TestRevocationServiceUnit:
    def test_purge_expired_revocations(self, client):
        # Génère au moins une révocation puis purge (les non-expirées restent)
        import datetime as dt

        from app.db.session import SessionLocal
        from app.models import RevokedToken
        from app.services.token_revocation import (
            is_access_token_revoked,
            purge_expired_revocations,
        )

        db = SessionLocal()
        try:
            # Une entrée déjà expirée
            db.add(
                RevokedToken(
                    jti="expired-jti",
                    user_id=None,
                    expires_at=dt.datetime(2000, 1, 1),
                )
            )
            # Une entrée encore valide
            db.add(
                RevokedToken(
                    jti="active-jti",
                    user_id=None,
                    expires_at=dt.datetime(2999, 1, 1),
                )
            )
            db.commit()
            removed = purge_expired_revocations(db)
            assert removed >= 1
            assert is_access_token_revoked("active-jti", db) is True
            assert is_access_token_revoked("expired-jti", db) is False
            assert is_access_token_revoked(None, db) is False
        finally:
            db.close()
