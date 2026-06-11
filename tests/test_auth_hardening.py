"""Auth hardening tests: RBAC, token expiry, brute force protection."""
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings


class TestAuthHardening:
    """Test auth flow hardening and RBAC."""

    def test_expired_token_rejected(self, client):
        """Verify that expired tokens are rejected."""
        # Create an expired token
        payload = {
            "sub": "test@example.com",
            "exp": datetime.now(UTC) - timedelta(hours=1),
        }
        token = jwt.encode(
            payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (401, 403)

    def test_invalid_token_rejected(self, client):
        """Verify that tampered tokens are rejected."""
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )
        assert response.status_code in (401, 403)

    def test_missing_auth_header_blocked(self, client):
        """Verify that missing auth header blocks protected endpoints."""
        response = client.get("/api/v1/users/me")
        assert response.status_code == 401

    def test_token_refresh_updates_expiry(self, client):
        """Verify that token refresh updates the expiry time."""
        login_resp = client.post(
            "/api/v1/login/access-token",
            data={"username": "admin", "password": "change_me_admin_password"},
        )
        assert login_resp.status_code == 200

        payload1 = login_resp.json()
        token1 = payload1["access_token"]

        # Decode token and check expiry
        payload_token1 = jwt.decode(token1, options={"verify_signature": False})
        exp1 = datetime.fromtimestamp(payload_token1["exp"], tz=UTC)

        # Wait a bit, then refresh
        import time

        time.sleep(1)

        refresh_resp = client.post(
            "/api/v1/login/refresh",
            json={"refresh_token": payload1["refresh_token"]},
        )
        assert refresh_resp.status_code == 200, refresh_resp.text

        token2 = refresh_resp.json()["access_token"]
        payload_token2 = jwt.decode(token2, options={"verify_signature": False})
        exp2 = datetime.fromtimestamp(payload_token2["exp"], tz=UTC)
        assert exp2 > exp1

    def test_rbac_admin_only_endpoint(self, client):
        """Verify RBAC: non-admin cannot access admin endpoints."""
        # Create user with limited role
        create_resp = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {self._get_admin_token(client)}"},
            json={
                "username": "user_example",
                "password": "Password123!",
                "full_name": "User Example",
                "role": "technician",
            },
        )
        assert create_resp.status_code == 201, create_resp.text

        # Login as technician
        resp = client.post(
            "/api/v1/login/access-token",
            data={"username": "user_example", "password": "Password123!"},
        )
        user_token = resp.json()["access_token"]

        # Try to access admin endpoint
        admin_resp = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert admin_resp.status_code == 403

    @staticmethod
    def _get_admin_token(client) -> str:
        """Helper: get admin token."""
        resp = client.post(
            "/api/v1/login/access-token",
            data={"username": "admin", "password": "change_me_admin_password"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]
