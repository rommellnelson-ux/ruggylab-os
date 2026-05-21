import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def test_cors_headers_present(client):
    """Test that CORS headers are added when enabled."""
    if not settings.CORS_ENABLED:
        pytest.skip("CORS not enabled")

    response = client.options(
        "/api/v1/login/access-token",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_user_quota_blocks_after_limit(client, monkeypatch):
    """Test that user quota middleware blocks after exceeding limit."""
    if not settings.USER_QUOTA_ENABLED:
        pytest.skip("User quota not enabled")

    # Temporarily increase rate limit and decrease quota for faster test
    original_rate_limit = settings.RATE_LIMIT_REQUESTS
    original_quota = settings.USER_QUOTA_REQUESTS
    settings.RATE_LIMIT_REQUESTS = 2000
    settings.USER_QUOTA_REQUESTS = 5

    try:
        # Login to get auth token
        response = client.post(
            "/api/v1/login/access-token",
            data={"username": "admin", "password": "change_me_admin_password"},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Mock authentication to set user_id
        def mock_auth_middleware(request, call_next):
            request.state.user_id = "test_user"
            return call_next(request)

        # Patch the middleware to simulate auth
        from app.core.user_quota import UserQuotaMiddleware
        original_dispatch = UserQuotaMiddleware.dispatch

        async def patched_dispatch(self, request, call_next):
            request.state.user_id = "test_user"
            return await original_dispatch(self, request, call_next)

        monkeypatch.setattr(UserQuotaMiddleware, "dispatch", patched_dispatch)

        # Make requests up to the limit
        for _ in range(settings.USER_QUOTA_REQUESTS):
            response = client.get("/api/v1/users/me", headers=headers)
            assert response.status_code == 200  # Now authenticated

        # Next request should be blocked
        response = client.get("/api/v1/users/me", headers=headers)
        assert response.status_code == 429
        assert "quota exceeded" in response.json()["detail"].lower()
    finally:
        settings.RATE_LIMIT_REQUESTS = original_rate_limit
        settings.USER_QUOTA_REQUESTS = original_quota
