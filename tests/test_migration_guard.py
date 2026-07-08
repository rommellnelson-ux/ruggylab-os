"""Verrou de migration : l'app refuse de servir un schéma qui n'est pas au head."""

import pytest
from sqlalchemy import create_engine, text

from app.db.migration_guard import assert_migrations_up_to_date, get_script_head


def _engine_with_revision(rev: str | None):
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        if rev:
            conn.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": rev})
    return eng


def test_schema_at_head_passes() -> None:
    assert_migrations_up_to_date(_engine_with_revision(get_script_head()))


def test_outdated_schema_raises_with_remediation() -> None:
    with pytest.raises(RuntimeError, match="upgrade head"):
        assert_migrations_up_to_date(_engine_with_revision("19990101_0000"))


def test_virgin_database_raises() -> None:
    # Base sans table alembic_version (jamais migrée) → refus explicite.
    with pytest.raises(RuntimeError, match="aucune révision"):
        assert_migrations_up_to_date(create_engine("sqlite://"))
