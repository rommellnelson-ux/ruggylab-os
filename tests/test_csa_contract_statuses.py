"""Tests de CONTRAT du flux sortant `labo_resultats` (§3 — gate pré-fusion).

Verrouille la matrice complète des états publiables et, surtout, l'invariant
qui protège le prescripteur : **aucun résultat non validé biologiquement ne
peut sortir sous une qualification biologique**.

Le contrat porte deux axes indépendants :

    etat_diffusion     : libere              (seul état poussé)
    validation.niveau  : biologique | auto | aucune

Un consommateur qui n'implémente qu'un seul axe doit lire `validation.niveau`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from pathlib import Path

import pytest

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.services.csa_sync.outbound import (
    CONTRAT_LABO_RESULTATS_VERSION,
    push_results,
)
from tests.test_csa_sync_outbound import (
    _FakeClient,
    _order_with_sample,
    _validated_result,
)


@pytest.fixture()
def db(tmp_path: Path) -> Generator[db_session.Session, None, None]:
    """Base jetable propre à ce module (la fixture n'est pas importée : F811)."""
    settings.TESTING = True
    db_session.configure_database(f"sqlite:///{tmp_path / 'csa_contract.db'}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)
    session = db_session.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=db_session.engine)


# Toute valeur de `statut` qui affirme une validation BIOLOGIQUE.
_STATUTS_AFFIRMANT_UNE_VALIDATION_BIOLOGIQUE = {"valide", "validated", "valid"}


def _push_one(db, **result_over) -> dict | None:
    """Crée un ordre CSA + un résultat, pousse, renvoie le payload (ou None)."""
    order = _order_with_sample(db, prescription_id=f"LAB-{result_over.pop('tag', 'X')}")
    _validated_result(db, order.sample_id, "GLYC", **result_over)
    client = _FakeClient()
    push_results(db, client)
    return client.pushed[0][2] if client.pushed else None


# ── matrice des quatre états ────────────────────────────────────────────────


def test_contract_biological_validation(db):
    payload = _push_one(db, tag="BIO", is_validated=True)
    assert payload is not None
    assert payload["contrat_version"] == CONTRAT_LABO_RESULTATS_VERSION
    assert payload["etat_diffusion"] == "libere"
    assert payload["validation"]["niveau"] == "biologique"
    assert payload["validation"]["mode_degrade"] is False
    assert payload["statut"] == "valide"


def test_contract_auto_validation(db):
    payload = _push_one(db, tag="AUTO", is_validated=False, is_auto_validated=True)
    assert payload is not None
    assert payload["etat_diffusion"] == "libere"
    assert payload["validation"]["niveau"] == "auto"
    # Diffusable, mais JAMAIS annoncé comme une validation biologique.
    assert payload["statut"] not in _STATUTS_AFFIRMANT_UNE_VALIDATION_BIOLOGIQUE
    assert payload["statut"] == "valide_auto"


def test_contract_released_without_validation(db):
    payload = _push_one(
        db,
        tag="DEGRADE",
        is_validated=False,
        is_auto_validated=False,
        released_at=dt.datetime(2026, 8, 1, 9),
    )
    assert payload is not None
    # Diffusion et validation divergent : c'est tout l'intérêt des deux axes.
    assert payload["etat_diffusion"] == "libere"
    assert payload["validation"]["niveau"] == "aucune"
    assert payload["validation"]["mode_degrade"] is True
    assert payload["statut"] not in _STATUTS_AFFIRMANT_UNE_VALIDATION_BIOLOGIQUE
    assert payload["statut"] == "libere_sans_validation"
    assert payload["validation"]["bio_validated_at"] is None


def test_contract_blocked_result_is_never_emitted(db):
    """Résultat non libérable : aucun payload ne sort. Pas d'état « bloqué » diffusé."""
    payload = _push_one(db, tag="BLOQUE", is_validated=False, is_auto_validated=False)
    assert payload is None, "un résultat non libérable ne doit jamais être publié"


# ── invariant central : ne jamais mentir sur la validation ──────────────────


@pytest.mark.parametrize(
    "tag,over,attendu_biologique",
    [
        ("I1", {"is_validated": True}, True),
        ("I2", {"is_validated": False, "is_auto_validated": True}, False),
        (
            "I3",
            {
                "is_validated": False,
                "is_auto_validated": False,
                "released_at": dt.datetime(2026, 8, 1, 9),
            },
            False,
        ),
    ],
)
def test_biological_claim_matches_reality(db, tag, over, attendu_biologique):
    """`statut` n'affirme une validation biologique que si elle a réellement eu lieu."""
    payload = _push_one(db, tag=tag, **over)
    assert payload is not None
    affirme_biologique = payload["statut"] in _STATUTS_AFFIRMANT_UNE_VALIDATION_BIOLOGIQUE
    assert affirme_biologique == attendu_biologique
    # Cohérence croisée des deux axes.
    assert (payload["validation"]["niveau"] == "biologique") == attendu_biologique


def test_no_legacy_field_reasserts_validated(db):
    """Aucun champ de compatibilité ne doit re-qualifier un résultat non validé.

    Garde-fou contre la « solution » tentante consistant à réintroduire un
    `legacy_status = "valide"` pour ne pas casser un ancien consommateur.
    """
    payload = _push_one(
        db,
        tag="NOLEGACY",
        is_validated=False,
        is_auto_validated=False,
        released_at=dt.datetime(2026, 8, 1, 9),
    )
    assert payload is not None
    for key, value in payload.items():
        if key == "validation" or not isinstance(value, str):
            continue
        assert value.strip().lower() not in _STATUTS_AFFIRMANT_UNE_VALIDATION_BIOLOGIQUE, (
            f"le champ {key!r} vaut {value!r} et re-qualifie un résultat non validé"
        )


def test_two_axes_are_independent(db):
    """Même `etat_diffusion`, `validation.niveau` différents : les axes ne fusionnent pas."""
    bio = _push_one(db, tag="AX1", is_validated=True)
    degrade = _push_one(
        db,
        tag="AX2",
        is_validated=False,
        is_auto_validated=False,
        released_at=dt.datetime(2026, 8, 1, 9),
    )
    assert bio["etat_diffusion"] == degrade["etat_diffusion"] == "libere"
    assert bio["validation"]["niveau"] != degrade["validation"]["niveau"]


# ── comportement du consommateur ────────────────────────────────────────────


def _consommateur_peut_afficher_comme_valide(payload: dict) -> bool:
    """Règle de lecture recommandée au consommateur CSA (documentée au runbook)."""
    return payload.get("validation", {}).get("niveau") == "biologique"


@pytest.mark.parametrize(
    "tag,over,affichable_comme_valide",
    [
        ("C1", {"is_validated": True}, True),
        ("C2", {"is_validated": False, "is_auto_validated": True}, False),
        (
            "C3",
            {
                "is_validated": False,
                "is_auto_validated": False,
                "released_at": dt.datetime(2026, 8, 1, 9),
            },
            False,
        ),
    ],
)
def test_documented_consumer_rule(db, tag, over, affichable_comme_valide):
    """La règle de lecture publiée donne bien le bon verdict pour chaque état."""
    payload = _push_one(db, tag=tag, **over)
    assert _consommateur_peut_afficher_comme_valide(payload) is affichable_comme_valide


def test_unknown_status_degrades_safely(db):
    """Un consommateur qui ne connaît que `valide` masque, il n'invente jamais.

    Vérifie la dégradation : les états non biologiques ne correspondent pas à
    `valide`, donc un ancien consommateur les ignore au lieu de les afficher
    à tort comme validés.
    """
    degrade = _push_one(
        db,
        tag="DEG2",
        is_validated=False,
        is_auto_validated=False,
        released_at=dt.datetime(2026, 8, 1, 9),
    )
    ancien_consommateur_affiche = degrade["statut"] == "valide"
    assert ancien_consommateur_affiche is False


def test_prescription_id_still_links_the_result(db):
    """La corrélation avec la prescription CSA reste possible dans le payload."""
    payload = _push_one(db, tag="LINK", is_validated=True)
    assert payload["prescription_id"] == "LAB-LINK"
    assert payload["exam_code"] == "GLYC"
