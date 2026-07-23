"""Contrôles statiques du vérificateur de restauration PostgreSQL.

Ces tests n'exécutent ni PowerShell, ni Docker, ni une commande SQL.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESTORE_SCRIPT = ROOT / "scripts" / "pg_restore_verify.ps1"


def _source() -> str:
    return RESTORE_SCRIPT.read_text(encoding="utf-8-sig")


def _assignment(module: ast.Module, name: str) -> Any:
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Affectation {name!r} absente.")


def _alembic_heads() -> set[str]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for migration in (ROOT / "alembic" / "versions").glob("*.py"):
        module = ast.parse(migration.read_text(encoding="utf-8-sig"))
        revision = _assignment(module, "revision")
        down_revision = _assignment(module, "down_revision")
        assert isinstance(revision, str)
        revisions.add(revision)
        if isinstance(down_revision, str):
            parents.add(down_revision)
        elif isinstance(down_revision, tuple):
            parents.update(parent for parent in down_revision if isinstance(parent, str))
    return revisions - parents


def test_scratch_database_is_guarded_before_first_drop() -> None:
    source = _source()
    guard_call = "Assert-SafeScratchDatabase $ScratchDb $PgDb"
    first_drop = '"DROP DATABASE IF EXISTS $ScratchDb;"'

    assert guard_call in source
    assert source.index(guard_call) < source.index(first_drop)
    assert "^ruggylab_verify(?:_[a-z0-9]+)?$" in source
    assert '"postgres", "template0", "template1", $ProductionDatabase' in source


@pytest.mark.parametrize(
    ("database_name", "allowed"),
    [
        ("ruggylab_verify", True),
        ("ruggylab_verify_ci123", True),
        ("ruggylab", False),
        ("postgres", False),
        ("ruggylab_verify;drop_database", False),
        ("other_scratch", False),
    ],
)
def test_scratch_database_name_policy(database_name: str, allowed: bool) -> None:
    source = _source()
    match = re.search(r"\$DatabaseName -notmatch '([^']+)'", source)
    assert match is not None

    assert (re.fullmatch(match.group(1), database_name, flags=re.IGNORECASE) is not None) is allowed


def test_cleanup_only_drops_a_scratch_database_created_by_this_run() -> None:
    source = _source()

    assert "$ScratchCreated = $false" in source
    assert "$ScratchCreated = $true" in source
    assert "if ($ScratchCreated -and -not $Keep)" in source


def test_checksum_sidecar_is_mandatory_for_verified_restore() -> None:
    source = _source()

    assert "Empreinte SHA-256 absente" in source
    assert "(pas de sidecar .sha256 — contrôle ignoré)" not in source


def test_pg_restore_failure_is_fatal() -> None:
    source = _source()

    assert "--exit-on-error" in source
    assert "$RestoreExitCode = $LASTEXITCODE" in source
    assert "if ($RestoreExitCode -ne 0)" in source


def test_expected_revision_matches_the_single_alembic_head() -> None:
    source = _source()
    match = re.search(r'\[string\]\$ExpectedHead\s*=\s*"([^"]+)"', source)
    assert match is not None

    heads = _alembic_heads()
    assert heads == {match.group(1)}


def test_operations_docs_use_postgresql_backup_tools() -> None:
    training = (ROOT / "docs" / "LIVRABLES_FORMATION_EXPLOITATION.md").read_text(
        encoding="utf-8-sig"
    )
    architecture = (ROOT / "docs" / "ARCHITECTURE_REVIEW.md").read_text(encoding="utf-8-sig")

    assert "scripts/pg_backup.ps1" in training
    assert "scripts/pg_restore_verify.ps1" in training
    assert "scripts/backup.ps1" not in training
    assert "scripts/restore.ps1" not in training
    assert "scripts/pg_backup.ps1" in architecture
    assert "scripts/pg_restore_verify.ps1" in architecture
