import logging
import os

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db import session as db_session
from app.db.base import Base
from app.models import User, UserRole

logger = logging.getLogger(__name__)


def init_db() -> None:
    # Verrou de migration : hors tests, refuser de servir une base dont le schéma
    # n'est pas au head Alembic embarqué (le service `migrate` est manuel — sans
    # ce verrou, l'omettre démarre l'app sur un schéma ancien). L'échec est
    # volontairement fatal : il remonte au lifespan et empêche le démarrage.
    if not settings.TESTING and os.getenv("SKIP_MIGRATION_CHECK") != "1":
        from app.db.migration_guard import assert_migrations_up_to_date

        assert_migrations_up_to_date(db_session.engine)

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
