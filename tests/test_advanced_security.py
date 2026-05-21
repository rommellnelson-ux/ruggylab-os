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


def test_user_quota_blocks_after_limit():
    """Test that UserQuotaMiddleware returns 429 after the per-user quota is reached.

    Uses a self-contained mini-app so it is independent of the shared conftest
    client (which sets TESTING=True and skips several middlewares).  A thin
    SetUserIDMiddleware sits in front of UserQuotaMiddleware and injects a
    synthetic user_id so the quota logic is exercised.
    """
    if not settings.USER_QUOTA_ENABLED:
        pytest.skip("User quota not enabled")

    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware

    from app.core.user_quota import UserQuotaMiddleware

    # -- Build minimal app ------------------------------------------------
    mini_app = FastAPI()

    @mini_app.get("/ping")
    def ping():
        return {"ok": True}

    class SetUserIDMiddleware(BaseHTTPMiddleware):
        """Injects a fixed user_id so UserQuotaMiddleware sees an auth'd user."""

        async def dispatch(self, request, call_next):
            request.state.user_id = "quota_test_user"
            return await call_next(request)

    # Starlette applies user-middlewares in LIFO order: add SetUserID *after*
    # UserQuota so that SetUserID runs *first* (outermost) in the call chain.
    mini_app.add_middleware(UserQuotaMiddleware)
    mini_app.add_middleware(SetUserIDMiddleware)

    # -- Configure a tight quota -------------------------------------------
    old_quota = settings.USER_QUOTA_REQUESTS
    old_window = settings.USER_QUOTA_WINDOW_SECONDS
    settings.USER_QUOTA_REQUESTS = 3
    settings.USER_QUOTA_WINDOW_SECONDS = 60

    try:
        with TestClient(mini_app, raise_server_exceptions=False) as tc:
            # First N requests must succeed
            for i in range(settings.USER_QUOTA_REQUESTS):
                resp = tc.get("/ping")
                assert resp.status_code == 200, f"Request {i + 1} unexpectedly failed"

            # One more request must be blocked
            resp = tc.get("/ping")
            assert resp.status_code == 429
            assert "quota exceeded" in resp.json()["detail"].lower()
    finally:
        settings.USER_QUOTA_REQUESTS = old_quota
        settings.USER_QUOTA_WINDOW_SECONDS = old_window
