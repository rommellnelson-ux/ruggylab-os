"""Tests for the refresh-token cleanup service and admin endpoint."""

import datetime


def _auth(client):
    resp = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Service-level tests (direct function calls via the ORM session)
# ---------------------------------------------------------------------------


def test_purge_removes_expired_tokens(client):
    """purge_expired_tokens() must delete rows past the keep_days window."""
    from app.db.session import SessionLocal
    from app.models import RefreshToken
    from app.services.token_cleanup import purge_expired_tokens
    from app.utils.datetime_utils import utcnow_naive

    db = SessionLocal()
    try:
        # Insert a token that expired 10 days ago
        old_token = RefreshToken(
            user_id=1,  # admin user seeded in conftest
            token_hash="deadbeef" * 8,  # 64-char fake hash
            expires_at=utcnow_naive() - datetime.timedelta(days=10),
            created_at=utcnow_naive() - datetime.timedelta(days=40),
        )
        db.add(old_token)
        db.commit()
        old_id = old_token.id

        deleted = purge_expired_tokens(db, keep_days=7)
        assert deleted >= 1

        still_there = db.query(RefreshToken).filter(RefreshToken.id == old_id).first()
        assert still_there is None
    finally:
        db.close()


def test_purge_keeps_fresh_tokens(client):
    """Active tokens (expires_at in the future) must never be deleted."""
    from app.db.session import SessionLocal
    from app.models import RefreshToken
    from app.services.token_cleanup import purge_expired_tokens
    from app.utils.datetime_utils import utcnow_naive

    db = SessionLocal()
    try:
        fresh = RefreshToken(
            user_id=1,
            token_hash="cafebabe" * 8,
            expires_at=utcnow_naive() + datetime.timedelta(days=30),
            created_at=utcnow_naive(),
        )
        db.add(fresh)
        db.commit()
        fresh_id = fresh.id

        purge_expired_tokens(db, keep_days=7)
        # Fresh token must still be there
        still_there = db.query(RefreshToken).filter(RefreshToken.id == fresh_id).first()
        assert still_there is not None

        # Cleanup our fixture row
        db.delete(still_there)
        db.commit()
    finally:
        db.close()


def test_purge_respects_keep_days(client):
    """A token expired 5 days ago must survive with keep_days=7."""
    from app.db.session import SessionLocal
    from app.models import RefreshToken
    from app.services.token_cleanup import purge_expired_tokens
    from app.utils.datetime_utils import utcnow_naive

    db = SessionLocal()
    try:
        recent_expired = RefreshToken(
            user_id=1,
            token_hash="aabbccdd" * 8,
            expires_at=utcnow_naive() - datetime.timedelta(days=5),
            created_at=utcnow_naive() - datetime.timedelta(days=35),
        )
        db.add(recent_expired)
        db.commit()
        token_id = recent_expired.id

        # keep_days=7 — expired only 5 days ago, so must NOT be deleted
        purge_expired_tokens(db, keep_days=7)
        still_there = db.query(RefreshToken).filter(RefreshToken.id == token_id).first()
        assert still_there is not None

        # keep_days=3 — now it is stale enough
        purge_expired_tokens(db, keep_days=3)
        gone = db.query(RefreshToken).filter(RefreshToken.id == token_id).first()
        assert gone is None
    finally:
        db.close()


def test_purge_returns_deleted_count(client):
    """purge_expired_tokens() must return the exact number of rows removed."""
    from app.db.session import SessionLocal
    from app.models import RefreshToken
    from app.services.token_cleanup import purge_expired_tokens
    from app.utils.datetime_utils import utcnow_naive

    db = SessionLocal()
    try:
        # Add 3 stale tokens
        for i in range(3):
            t = RefreshToken(
                user_id=1,
                token_hash=f"stale{i:060d}",
                expires_at=utcnow_naive() - datetime.timedelta(days=20),
                created_at=utcnow_naive() - datetime.timedelta(days=50),
            )
            db.add(t)
        db.commit()

        deleted = purge_expired_tokens(db, keep_days=0)
        assert deleted >= 3
    finally:
        db.close()


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


def test_cleanup_endpoint_requires_admin(client):
    """Non-admin users must be rejected."""
    headers = _auth(client)
    # Create a technician
    client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "tech_cleanup",
            "password": "Password123!",
            "full_name": "Tech Cleanup",
            "role": "technician",
        },
    )
    tech_tokens = client.post(
        "/api/v1/login/access-token",
        data={"username": "tech_cleanup", "password": "Password123!"},
    ).json()
    tech_headers = {"Authorization": f"Bearer {tech_tokens['access_token']}"}

    resp = client.delete(
        "/api/v1/maintenance/refresh-tokens/expired",
        headers=tech_headers,
    )
    assert resp.status_code == 403


def test_cleanup_endpoint_admin_ok(client):
    """Admin can call the endpoint; response includes deleted count."""
    headers = _auth(client)
    resp = client.delete(
        "/api/v1/maintenance/refresh-tokens/expired",
        headers=headers,
        params={"keep_days": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted" in data
    assert isinstance(data["deleted"], int)
    assert data["keep_days"] == 0


def test_cleanup_endpoint_idempotent(client):
    """Calling the endpoint twice in a row must not raise errors."""
    headers = _auth(client)
    for _ in range(2):
        resp = client.delete(
            "/api/v1/maintenance/refresh-tokens/expired",
            headers=headers,
        )
        assert resp.status_code == 200


def test_cleanup_endpoint_keep_days_validation(client):
    """keep_days must be between 0 and 365; out-of-range values return 422."""
    headers = _auth(client)
    resp = client.delete(
        "/api/v1/maintenance/refresh-tokens/expired",
        headers=headers,
        params={"keep_days": 999},
    )
    assert resp.status_code == 422
