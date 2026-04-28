import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base import Base
from app.db import session as db_session
from app.models import User, UserRole


logger = logging.getLogger(__name__)


def init_db() -> None:
    try:
        Base.metadata.create_all(bind=db_session.engine)
        _seed_first_superuser()
    except SQLAlchemyError as exc:
        logger.warning("Database initialization skipped: %s", exc)


def _seed_first_superuser() -> None:
    if not settings.TESTING and settings.requires_security_hardening:
        logger.warning(
            "Skipping superuser seeding because security settings are still using weak non-test values."
        )
        return

    db: Session = db_session.SessionLocal()
    try:
        existing_user = db.query(User).filter(User.username == settings.FIRST_SUPERUSER).first()
        if existing_user:
            return

        user = User(
            username=settings.FIRST_SUPERUSER,
            hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
            full_name=settings.FIRST_SUPERUSER_FULL_NAME,
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        logger.info("Seeded initial admin user: %s", settings.FIRST_SUPERUSER)
    finally:
        db.close()
