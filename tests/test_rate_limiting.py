from pathlib import Path

from fastapi.testclient import TestClient

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.main import create_app


def test_rate_limiting_blocks_after_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "test_ruggylab_rate_limit.db"
    settings.TESTING = False
    settings.ENABLE_DH36_LISTENER = False
    settings.SECRET_KEY = "VeryStrongSecretKeyValue1234567890Secure"
    settings.FIRST_SUPERUSER = "admin"
    settings.FIRST_SUPERUSER_PASSWORD = "SuperSecurePassphrase2026!"
    settings.FIRST_SUPERUSER_FULL_NAME = "RuggyLab Administrator"
    settings.RATE_LIMIT_ENABLED = True
    settings.RATE_LIMIT_REQUESTS = 3
    settings.RATE_LIMIT_WINDOW_SECONDS = 30
    settings.RATE_LIMIT_BLOCK_SECONDS = 60

    db_session.configure_database(f"sqlite:///{database_path}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)

    app = create_app()
    with TestClient(app) as client:
        for _ in range(settings.RATE_LIMIT_REQUESTS):
            response = client.get("/")
            assert response.status_code == 200

        response = client.get("/")
        assert response.status_code == 429
        assert response.json()["detail"] == "Rate limit exceeded"
