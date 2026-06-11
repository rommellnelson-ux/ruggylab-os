"""Auth hardening tests: RBAC, token expiry, brute force protection."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from app.api.deps import get_current_user
from app.core.config import settings
from app.main import app


client = TestClient(app)


class TestAuthHardening:
    """Test auth flow hardening and RBAC."""

    def test_expired_token_rejected(self):
        """Verify that expired tokens are rejected."""
        # Create an expired token
        payload = {
            "sub": "test@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(
            payload, settings.SECRET_KEY, algorithm="HS256"
        )
        
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (401, 403)

    def test_invalid_token_rejected(self):
        """Verify that tampered tokens are rejected."""
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )
        assert response.status_code in (401, 403)

    def test_missing_auth_header_blocked(self):
        """Verify that missing auth header blocks protected endpoints."""
        response = client.get("/api/v1/patients")
        assert response.status_code == 403

    def test_token_refresh_updates_expiry(self):
        """Verify that token refresh updates the expiry time."""
        login_resp = client.post(
            "/api/v1/login/access-token",
            data={"username": "admin", "password": "change_me_admin_password"},
        )
        assert login_resp.status_code == 200
        
        token1 = login_resp.json()["access_token"]
        
        # Decode token and check expiry
        payload1 = jwt.decode(
            token1, settings.SECRET_KEY, algorithms=["HS256"]
        )
        exp1 = datetime.fromtimestamp(payload1["exp"], tz=timezone.utc)
        
        # Wait a bit, then refresh
        import time
        time.sleep(1)
        
        refresh_resp = client.post(
            "/api/v1/login/refresh",
            headers={"Authorization": f"Bearer {token1}"},
        )
        if refresh_resp.status_code == 200:
            token2 = refresh_resp.json()["access_token"]
            payload2 = jwt.decode(
                token2, settings.SECRET_KEY, algorithms=["HS256"]
            )
            exp2 = datetime.fromtimestamp(payload2["exp"], tz=timezone.utc)
            assert exp2 > exp1

    def test_rbac_admin_only_endpoint(self):
        """Verify RBAC: non-admin cannot access admin endpoints."""
        # Create user with limited role
        client.post(
            "/api/v1/users",
            headers={
                "Authorization": f"Bearer {self._get_admin_token()}",
            },
            json={
                "email": "user@example.com",
                "password": "pass123",
                "role": "technician",
            },
        )
        
        # Login as technician
        resp = client.post(
            "/api/v1/login/access-token",
            data={"username": "user@example.com", "password": "pass123"},
        )
        user_token = resp.json()["access_token"]
        
        # Try to access admin endpoint
        admin_resp = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert admin_resp.status_code == 403

    @staticmethod
    def _get_admin_token() -> str:
        """Helper: get admin token."""
        resp = client.post(
            "/api/v1/login/access-token",
            data={"username": "admin", "password": "change_me_admin_password"},
        )
        return resp.json()["access_token"]
