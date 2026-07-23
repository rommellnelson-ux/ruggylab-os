"""Alembic migration integrity tests.

Verifies that every migration in alembic/versions/ can be:
1. Applied to a fresh SQLite database (upgrade head)
2. Rolled back to the base (downgrade base)
3. Re-applied cleanly (upgrade head again)

This catches broken down() functions early without needing a PostgreSQL
service container (which is tested separately in CI via the test-postgres
GitHub Actions job).
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect


@pytest.fixture
def alembic_engine(tmp_path):
    """SQLite engine pointing at a fresh temp DB for migration testing."""
    db_url = f"sqlite:///{tmp_path / 'migration_test.db'}"
    engine = create_engine(db_url)
    yield engine
    engine.dispose()


def _run_alembic(command: str, db_url: str) -> None:
    """Run an alembic CLI command with the given DATABASE_URL.

    ``command`` is a space-separated string such as ``"upgrade head"`` or
    ``"downgrade base"``; it is split into tokens before being passed to
    subprocess so each token is a distinct argument.
    """
    import os
    import subprocess
    import sys

    full_env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *command.split()],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(Path(__file__).parent.parent),  # repo root
    )
    if result.returncode != 0:
        raise AssertionError(f"alembic {command} failed:\n{result.stdout}\n{result.stderr}")


@pytest.mark.parametrize("dummy", [None])  # run once, named for clarity
def test_migrations_upgrade_head(tmp_path, dummy):
    """alembic upgrade head must apply all migrations without errors."""
    db_url = f"sqlite:///{tmp_path / 'up.db'}"
    _run_alembic("upgrade head", db_url)

    engine = create_engine(db_url)
    insp = inspect(engine)
    tables = insp.get_table_names()
    engine.dispose()

    # Core tables must exist after upgrade
    assert "users" in tables
    assert "patients" in tables
    assert "results" in tables
    assert "refresh_tokens" in tables
    assert "auth_version" in {column["name"] for column in insp.get_columns("users")}


def test_migrations_downgrade_base(tmp_path):
    """alembic downgrade base must cleanly undo all migrations."""
    db_url = f"sqlite:///{tmp_path / 'down.db'}"
    _run_alembic("upgrade head", db_url)
    _run_alembic("downgrade base", db_url)

    engine = create_engine(db_url)
    insp = inspect(engine)
    tables = insp.get_table_names()
    engine.dispose()

    # After full downgrade only alembic_version table (or nothing) should remain
    assert "users" not in tables
    assert "refresh_tokens" not in tables


def test_migrations_idempotent_roundtrip(tmp_path):
    """upgrade → downgrade → upgrade must succeed without errors."""
    db_url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    _run_alembic("upgrade head", db_url)
    _run_alembic("downgrade base", db_url)
    _run_alembic("upgrade head", db_url)

    engine = create_engine(db_url)
    insp = inspect(engine)
    tables = insp.get_table_names()
    engine.dispose()

    assert "users" in tables
    assert "refresh_tokens" in tables


def test_alembic_history_is_linear(tmp_path):
    """Every revision must have exactly one predecessor (no diverging branches)."""
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "history", "--verbose"],
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'hist.db'}"},
        cwd=str(Path(__file__).parent.parent),  # repo root
    )
    assert result.returncode == 0, result.stderr

    # Ensure no "branched" marker appears in the output
    assert "branch" not in result.stdout.lower() or "no branches" in result.stdout.lower(), (
        f"Alembic history contains unexpected branches:\n{result.stdout}"
    )
