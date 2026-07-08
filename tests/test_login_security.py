from pathlib import Path

from fastapi.testclient import TestClient

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.main import create_app


def test_security_headers_are_present(tmp_path: Path) -> None:
    database_path = tmp_path / "test_ruggylab_security_headers.db"
    settings.TESTING = True
    settings.ENABLE_DH36_LISTENER = False
    settings.SECRET_KEY = "StrongSecretKeyValue1234567890Secure"
    settings.FIRST_SUPERUSER = "admin"
    settings.FIRST_SUPERUSER_PASSWORD = "SuperSecurePassphrase2026!"
    settings.FIRST_SUPERUSER_FULL_NAME = "RuggyLab Administrator"
    settings.RATE_LIMIT_ENABLED = False
    settings.LOGIN_RATE_LIMIT_ENABLED = True

    db_session.configure_database(f"sqlite:///{database_path}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "geolocation=(), microphone=(), camera=()"
    assert "X-XSS-Protection" in response.headers


def test_login_rate_limit_blocks_after_limit(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    database_path = tmp_path / "test_ruggylab_login_rate_limit.db"
    # TESTING=False pour activer le rate limiting, mais le schéma vient de
    # create_all (pas d'alembic_version) : on débraye le verrou de migration.
    monkeypatch.setenv("SKIP_MIGRATION_CHECK", "1")
    settings.TESTING = False
    settings.ENABLE_DH36_LISTENER = False
    settings.SECRET_KEY = "StrongSecretKeyValue1234567890Secure"
    settings.FIRST_SUPERUSER = "admin"
    settings.FIRST_SUPERUSER_PASSWORD = "SuperSecurePassphrase2026!"
    settings.FIRST_SUPERUSER_FULL_NAME = "RuggyLab Administrator"
    settings.LOGIN_RATE_LIMIT_ENABLED = True
    settings.LOGIN_RATE_LIMIT_REQUESTS = 3
    settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS = 30
    settings.LOGIN_RATE_LIMIT_BLOCK_SECONDS = 60
    settings.RATE_LIMIT_ENABLED = False
    settings.METRICS_SERVER_ENABLED = False

    db_session.configure_database(f"sqlite:///{database_path}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)

    app = create_app()
    with TestClient(app) as client:
        for _ in range(settings.LOGIN_RATE_LIMIT_REQUESTS):
            response = client.post(
                "/api/v1/login/access-token",
                data={"username": "invalid_user", "password": "wrong_password"},
            )
            assert response.status_code == 401

        blocked_response = client.post(
            "/api/v1/login/access-token",
            data={"username": "invalid_user", "password": "wrong_password"},
        )

    assert blocked_response.status_code == 429
    assert blocked_response.json()["detail"] == "Too many login attempts."
    assert blocked_response.headers["Retry-After"] == str(settings.LOGIN_RATE_LIMIT_BLOCK_SECONDS)
