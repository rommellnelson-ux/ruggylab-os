from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test_ruggylab.db"
    settings.TESTING = True
    settings.ENABLE_DH36_LISTENER = False
    settings.SECRET_KEY = "test_secret_key_for_pytest_only_123456"
    settings.FIRST_SUPERUSER = "admin"
    settings.FIRST_SUPERUSER_PASSWORD = "change_me_admin_password"
    settings.FIRST_SUPERUSER_FULL_NAME = "RuggyLab Administrator"
    db_session.configure_database(f"sqlite:///{database_path}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=db_session.engine)
