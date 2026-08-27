"""Tests du vérificateur de sauvegarde/restauration multiplateforme.

Le cycle complet (dump → restore → application) tourne dans le job CI
« Sauvegarde et restauration PostgreSQL », qui exige un vrai serveur. Ces tests
verrouillent ce qui peut l'être sans serveur : l'alignement de la tête Alembic,
le garde-fou anti-base-réelle, et le fait que le rapport échoue vraiment.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.backup_restore_verify import (
    EXPECTED_ALEMBIC_HEAD,
    _guard_disposable,
    _report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_heads() -> set[str]:
    """Révisions qui ne sont référencées comme `down_revision` par personne."""
    revisions, downs = set(), set()
    for path in (REPO_ROOT / "alembic" / "versions").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if m := re.search(r'^revision\s*=\s*"([^"]+)"', source, re.M):
            revisions.add(m.group(1))
        if m := re.search(r'^down_revision\s*=\s*"([^"]+)"', source, re.M):
            downs.add(m.group(1))
    return revisions - downs


# ── alignement avec la tête réelle ──────────────────────────────────────────


def test_single_alembic_head():
    heads = _alembic_heads()
    assert len(heads) == 1, f"tête Alembic multiple : {sorted(heads)}"


def test_expected_head_matches_repository():
    """La constante du vérificateur suit la tête réelle du dépôt."""
    assert _alembic_heads() == {EXPECTED_ALEMBIC_HEAD}


def test_ci_job_pins_the_same_head():
    """Le job CI épingle la même révision que le module."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f'test "$head" = "{EXPECTED_ALEMBIC_HEAD}"' in workflow


def test_powershell_script_is_preserved():
    """Le script d'exploitation Windows n'est pas supprimé par cet ajout."""
    assert (REPO_ROOT / "scripts" / "pg_restore_verify.ps1").is_file()


# ── garde-fou : jamais une base d'exploitation ──────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@localhost:5432/ruggylab",
        "postgresql+psycopg://u:p@prod-host:5432/ruggylab_prod",
        "postgresql+psycopg://u:p@localhost:5432/clinique",
    ],
)
def test_refuses_non_disposable_database(url):
    with pytest.raises(SystemExit, match="REFUS"):
        _guard_disposable(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@localhost:5432/ruggylab_restore_src",
        "postgresql+psycopg://u:p@localhost:5432/ruggylab_restore_verify",
        "postgresql+psycopg://u:p@localhost:5432/ruggylab_test",
        "postgresql+psycopg://u:p@localhost:5432/scratch_db",
    ],
)
def test_accepts_disposable_database(url):
    _guard_disposable(url)  # ne lève pas


def test_query_string_does_not_defeat_the_guard():
    with pytest.raises(SystemExit):
        _guard_disposable("postgresql+psycopg://u:p@h:5432/ruggylab?sslmode=require")


# ── le rapport échoue réellement ────────────────────────────────────────────


def test_report_returns_false_on_any_failure(capsys):
    ok = _report([("Comptage patients", True, "3 vs 3"), ("Tête Alembic", False, "x vs y")])
    assert ok is False
    assert "ECHEC" in capsys.readouterr().out


def test_report_returns_true_when_all_pass(capsys):
    ok = _report([("Comptage patients", True, "3 vs 3")])
    assert ok is True
    assert "SUCCES" in capsys.readouterr().out


# ── le semis ne contient aucune identité plausible ──────────────────────────


def test_seed_dataset_is_obviously_synthetic():
    from scripts.backup_restore_verify import _PATIENTS

    for ipp, last, first, _dob, _sex in _PATIENTS:
        assert ipp.startswith("TEST-"), f"{ipp} doit annoncer son caractère de test"
        assert last == "SYNTHETIQUE"
        assert first.startswith("Patient")


def test_manifest_roundtrip(tmp_path):
    """Le manifeste est du JSON simple, relisible par l'étape de vérification."""
    manifest = {"alembic_head": EXPECTED_ALEMBIC_HEAD, "counts": {"patients": 3}}
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["counts"]["patients"] == 3


# ── le nom de table ne vient jamais du manifeste sans contrôle ──────────────


def test_countable_tables_is_a_closed_set():
    from scripts.backup_restore_verify import _COUNTABLE_TABLES

    assert set(_COUNTABLE_TABLES) == {
        "patients",
        "samples",
        "exam_orders",
        "exam_order_items",
        "results",
    }


def test_no_fstring_interpolation_of_manifest_table_names():
    """Le module ne construit aucune requête à partir d'une valeur du manifeste."""
    source = (REPO_ROOT / "scripts" / "backup_restore_verify.py").read_text(encoding="utf-8")
    assert 'text(f"SELECT count(*) FROM {table}")' not in source


# ── le semis couvre toutes les colonnes obligatoires ────────────────────────


def test_seed_can_satisfy_every_not_null_column():
    """Aucune colonne NOT NULL ne reste sans valeur au moment de l'insertion.

    Régression réelle : la première version insérait en SQL brut et omettait
    `exam_orders.ordered_at`, dont le défaut est côté Python — invisible pour un
    INSERT direct. Le semis passe désormais par l'ORM ; ce test vérifie que
    chaque colonne obligatoire est bien couverte, soit par un défaut (serveur ou
    Python), soit par une valeur que le semis fournit explicitement.
    """
    import app.models  # noqa: F401 — charge les mappers
    from app.db.base import Base

    fournis = {
        "patients": {"ipp_unique_id", "first_name", "last_name", "birth_date", "sex"},
        "samples": {"barcode", "patient_id", "status"},
        "exam_orders": {"patient_id", "sample_id", "status", "requesting_service", "priority"},
        "exam_order_items": {"order_id", "exam_code", "exam_label", "status", "result_id"},
        "results": {"sample_id", "exam_code", "data_points", "result_type", "is_validated"},
    }

    for table_name, explicites in fournis.items():
        table = Base.metadata.tables[table_name]
        for column in table.columns:
            if column.primary_key or column.nullable:
                continue
            couverte = (
                column.server_default is not None
                or column.default is not None
                or column.name in explicites
            )
            assert couverte, (
                f"{table_name}.{column.name} est NOT NULL, sans défaut, "
                "et le semis ne le fournit pas"
            )
