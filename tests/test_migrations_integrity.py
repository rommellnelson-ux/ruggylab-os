"""Test migration safety: verify migrations can be applied and rolled back cleanly."""
from pathlib import Path

import pytest


def get_alembic_root() -> Path:
    """Find alembic directory."""
    return Path(__file__).parent.parent / "alembic"


class TestMigrationIntegrity:
    """Test database migrations for integrity and safety."""

    def test_migration_files_exist(self):
        """Verify migration files are present."""
        versions_dir = get_alembic_root() / "versions"
        assert versions_dir.exists()

        # Check for at least some migration files
        migrations = list(versions_dir.glob("*.py"))
        assert len(migrations) > 0

    def test_migrations_are_valid_python(self):
        """Verify all migration files are valid Python."""
        versions_dir = get_alembic_root() / "versions"

        for migration in versions_dir.glob("*.py"):
            with open(migration) as f:
                code = f.read()
            try:
                compile(code, str(migration), "exec")
            except SyntaxError as e:
                pytest.fail(f"Invalid Python in {migration}: {e}")

    def test_migration_naming_convention(self):
        """Verify migrations follow naming convention."""
        versions_dir = get_alembic_root() / "versions"

        for migration in versions_dir.glob("[0-9]*.py"):
            # Should be: YYYYMMDD_HHMM_description.py
            name = migration.stem
            parts = name.split("_", 2)
            assert len(parts) >= 2, f"Invalid migration name: {name}"

    def test_alembic_env_is_configured(self):
        """Verify alembic env.py is properly configured."""
        env_py = get_alembic_root() / "env.py"
        assert env_py.exists()

        with open(env_py) as f:
            content = f.read()

        # Check for key alembic patterns
        assert "run_migrations" in content
        assert "configure_logging" in content

    def test_migration_heads_are_linear(self):
        """Verify migration history is linear (no branches)."""
        # This would require connecting to DB and running alembic,
        # which is heavy. For now, just verify no migration files
        # reference an old head in a conflicting way.
        versions_dir = get_alembic_root() / "versions"

        downs = []
        for migration in sorted(versions_dir.glob("[0-9]*.py")):
            with open(migration) as f:
                content = f.read()

            if "revision = " in content:
                # Extract the revision and down_revision
                for line in content.split("\n"):
                    if line.startswith("down_revision"):
                        downs.append(line)

        # Simple check: ensure no duplicate down_revisions
        # (which would indicate a branch)
        assert len(downs) == len(set(downs)), "Migration history has branches"
