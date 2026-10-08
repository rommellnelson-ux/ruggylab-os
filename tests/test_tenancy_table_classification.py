"""Tests — la classification de tenancy couvre 100 % du schéma, et le dit encore demain.

ADR-001 exige que toute table soit classée (GLOBAL, TENANT, SITE, UNIT,
TECHNICAL ou TBD) avant d'être tenantisée. Une table ajoutée au modèle sans
passer par `docs/architecture/TENANCY_TABLE_CLASSIFICATION.md` est une table
dont personne n'a décidé à qui elle appartient : ces tests la refusent.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

import app.models
from app.db.base import Base

# `app.db.base` n'enregistre pas tous les modules de modèles (cf. rapport de gate,
# P0-3 FOUNDATION_SCHEMA_REGISTRATION_GAP) : on les importe tous pour juger le schéma complet.
for _module in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_module.name}")

REPO_ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = REPO_ROOT / "docs" / "architecture" / "TENANCY_TABLE_CLASSIFICATION.md"

SCOPES_AUTORISES = {"GLOBAL", "TENANT", "SITE", "UNIT", "TECHNICAL", "TBD"}

# Une ligne de classification : | `table` | sens métier | SCOPE | ...
_LIGNE = re.compile(r"^\| `(?P<table>[a-z_0-9]+)` \| [^|]+\| (?P<scope>[A-Z]+) \|", re.MULTILINE)
_SYNTHESE = re.compile(r"^\| (?P<scope>[A-Z]+) \| (?P<n>\d+) \|$", re.MULTILINE)
_TBD = re.compile(r"^\| TBD-\d+ \| `(?P<table>[a-z_0-9]+)` \|(?P<reste>.*)$", re.MULTILINE)


def _classification() -> dict[str, str]:
    texte = CLASSIFICATION.read_text(encoding="utf-8")
    lignes = [(m["table"], m["scope"]) for m in _LIGNE.finditer(texte)]
    doublons = [t for t, n in Counter(t for t, _ in lignes).items() if n > 1]
    assert not doublons, f"tables classées plusieurs fois : {doublons}"
    return dict(lignes)


def ecarts(tables_schema: set[str], classees: dict[str, str]) -> dict[str, list[str]]:
    """Écarts entre le schéma et la classification (vide = conforme)."""
    return {
        "non_classees": sorted(tables_schema - classees.keys()),
        "obsoletes": sorted(classees.keys() - tables_schema),
        "scope_invalide": sorted(t for t, s in classees.items() if s not in SCOPES_AUTORISES),
    }


def test_toute_table_du_schema_est_classee():
    classees = _classification()
    resultat = ecarts(set(Base.metadata.tables), classees)
    assert resultat == {"non_classees": [], "obsoletes": [], "scope_invalide": []}


def test_une_nouvelle_table_sans_classification_est_detectee():
    classees = _classification()
    schema = set(Base.metadata.tables) | {"nouvelle_table_non_classee"}
    assert ecarts(schema, classees)["non_classees"] == ["nouvelle_table_non_classee"]


def test_un_scope_hors_liste_est_detecte():
    classees = {**_classification(), "patients": "SHARED"}
    assert ecarts(set(Base.metadata.tables), classees)["scope_invalide"] == ["patients"]


def test_la_synthese_correspond_aux_lignes():
    texte = CLASSIFICATION.read_text(encoding="utf-8")
    annonce = {m["scope"]: int(m["n"]) for m in _SYNTHESE.finditer(texte)}
    reel = Counter(_classification().values())
    assert annonce == {s: reel.get(s, 0) for s in annonce}
    assert set(annonce) == SCOPES_AUTORISES


def test_une_table_classee_qui_n_existe_plus_est_detectee():
    classees = {**_classification(), "table_supprimee": "TENANT"}
    assert ecarts(set(Base.metadata.tables), classees)["obsoletes"] == ["table_supprimee"]


def test_une_classification_en_double_est_detectee(tmp_path, monkeypatch):
    double = tmp_path / "classification.md"
    double.write_text(
        "| `exam_tariffs` | Tarifs | TENANT |\n| `exam_tariffs` | Tarifs | GLOBAL |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "CLASSIFICATION", double)
    with pytest.raises(AssertionError, match="plusieurs fois"):
        _classification()


# Constat FOUNDATION_SCHEMA_REGISTRATION_GAP (rapport de gate 2026-10-07) : documenté,
# non corrigé dans ce lot. `strict=True` : ce test deviendra rouge (XPASS) le jour où
# la remédiation aura lieu, pour forcer la mise à jour du rapport et le retrait du marqueur.
TABLES_HORS_METADONNEE_ALEMBIC = {"aes_incidents", "epi_notifications", "reagent_lots"}


def _tables_vues_par_alembic() -> set[str]:
    """Tables de `app.db.base.Base.metadata` (la cible d'`alembic/env.py`), dans un
    interpréteur neuf : le résultat ne dépend pas des imports faits par ce module."""
    script = (
        "import json; from app.db.base import Base; print(json.dumps(sorted(Base.metadata.tables)))"
    )
    sortie = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return set(json.loads(sortie.stdout.strip().splitlines()[-1]))


@pytest.mark.xfail(strict=True, reason="FOUNDATION_SCHEMA_REGISTRATION_GAP = OPEN")
def test_la_metadonnee_alembic_enregistre_toutes_les_tables():
    vues_par_alembic = _tables_vues_par_alembic()
    manquantes = set(Base.metadata.tables) - vues_par_alembic
    assert manquantes == set(), f"absentes de app.db.base : {sorted(manquantes)}"


def test_l_ecart_de_metadonnee_alembic_est_exactement_celui_documente():
    vues_par_alembic = _tables_vues_par_alembic()
    assert len(Base.metadata.tables) == 49
    assert len(vues_par_alembic) == 46
    assert set(Base.metadata.tables) - vues_par_alembic == TABLES_HORS_METADONNEE_ALEMBIC


def test_chaque_tbd_a_raison_proprietaire_et_question():
    texte = CLASSIFICATION.read_text(encoding="utf-8")
    tbd_classes = {t for t, s in _classification().items() if s == "TBD"}
    documentes = {}
    for m in _TBD.finditer(texte):
        cellules = [c.strip() for c in m["reste"].strip().strip("|").split("|")]
        assert len(cellules) == 3 and all(cellules), f"TBD incomplet : {m['table']}"
        documentes[m["table"]] = cellules
    assert set(documentes) == tbd_classes
