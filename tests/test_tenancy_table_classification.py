"""Tests — la classification de tenancy couvre 100 % du schéma, et le dit encore demain.

ADR-001 exige que toute table soit classée (GLOBAL, TENANT, SITE, UNIT,
TECHNICAL ou TBD) avant d'être tenantisée. Une table ajoutée au modèle sans
passer par `docs/architecture/TENANCY_TABLE_CLASSIFICATION.md` est une table
dont personne n'a décidé à qui elle appartient : ces tests la refusent.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections import Counter
from pathlib import Path

import app.models
from app.db.base import Base

# `app.db.base` n'enregistre pas tous les modules de modèles (cf. rapport de gate,
# P1-ALEMBIC-METADATA) : on les importe tous pour juger le schéma complet.
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


def test_chaque_tbd_a_raison_proprietaire_et_question():
    texte = CLASSIFICATION.read_text(encoding="utf-8")
    tbd_classes = {t for t, s in _classification().items() if s == "TBD"}
    documentes = {}
    for m in _TBD.finditer(texte):
        cellules = [c.strip() for c in m["reste"].strip().strip("|").split("|")]
        assert len(cellules) == 3 and all(cellules), f"TBD incomplet : {m['table']}"
        documentes[m["table"]] = cellules
    assert set(documentes) == tbd_classes
