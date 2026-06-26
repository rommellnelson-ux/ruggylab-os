"""Tests — jeu de données de démonstration UAT (validité des lignes registre)."""

from __future__ import annotations

from app.services.registre_parser import build_import_preview
from scripts.seed_demo import DEMO_REGISTRE_ROWS, DEMO_RICH


def test_demo_rows_well_formed():
    assert len(DEMO_REGISTRE_ROWS) >= 10
    for row in DEMO_REGISTRE_ROWS:
        assert row.get("nom")
        assert row.get("examens")


def test_demo_rows_high_recognition():
    preview = build_import_preview(DEMO_REGISTRE_ROWS)
    # Forte reconnaissance attendue ; quelques examens (GGT, TPHA, VDRL) existent
    # au référentiel bioref mais pas au catalogue d'examens du registre.
    assert preview["recognition_rate_pct"] >= 85.0


def test_demo_rich_specs_shape():
    for name, sex, exam_code, data, tat_kind in DEMO_RICH:
        assert name and exam_code and isinstance(data, dict)
        assert sex in ("M", "F")
        assert tat_kind in ("on_time", "late")
