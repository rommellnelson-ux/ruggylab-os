"""Tests du flux sortant d'intégration CSA (phase I2) : résultats → labo_resultats."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.models import ExamOrder, Result, Sample
from app.services.csa_sync.inbound import apply_prescription
from app.services.csa_sync.outbound import push_results


@pytest.fixture()
def db(tmp_path: Path) -> Generator[db_session.Session, None, None]:
    settings.TESTING = True
    db_session.configure_database(f"sqlite:///{tmp_path / 'csa_out.db'}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)
    session = db_session.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=db_session.engine)


class _FakeClient:
    def __init__(self, fail: bool = False):
        self.pushed: list = []
        self.fail = fail

    def push_event(self, kind, source_item_id, payload):
        if self.fail:
            raise RuntimeError("réseau CSA indisponible")
        self.pushed.append((kind, source_item_id, payload))
        return f"{kind}:{source_item_id}"


def _presc(**over) -> dict:
    base = {
        "prescription_id": "LAB-1",
        "dossier_no": "CSA-0001",
        "patient_nom": "DIOMANDE Kenza",
        "date_naissance": "1990-06-15",
        "sexe": "F",
        "examens": [{"code": "BNDA008", "nom": "Glycémie"}],  # -> GLYC
    }
    base.update(over)
    return base


def _order_with_sample(db, **presc_over) -> ExamOrder:
    """Ordre CSA + échantillon rattaché (état « prélevé »)."""
    order = apply_prescription(db, _presc(**presc_over))
    db.flush()
    sample = Sample(barcode=f"B-{order.id}", patient_id=order.patient_id, status="received")
    db.add(sample)
    db.flush()
    order.sample_id = sample.id
    db.commit()
    return order


def _validated_result(db, sample_id: int, exam_code: str, **over) -> Result:
    fields = {
        "sample_id": sample_id,
        "exam_code": exam_code,
        "data_points": {exam_code: {"value": 0.95, "unit": "g/L", "status": "N"}},
        "result_type": "quantitative",
        "is_validated": True,
    }
    fields.update(over)  # permet de surcharger is_validated / released_at / ...
    result = Result(**fields)
    db.add(result)
    db.commit()
    return result


# ── cas nominal ─────────────────────────────────────────────────────────────
def test_pushes_validated_result(db):
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC")

    client = _FakeClient()
    res = push_results(db, client)

    assert res["pushed"] == 1
    kind, source_item_id, payload = client.pushed[0]
    assert kind == "labo_resultats"
    assert source_item_id == "LAB-1:GLYC"
    assert payload["prescription_id"] == "LAB-1"
    assert payload["exam_code"] == "GLYC"
    assert payload["statut"] == "valide"
    assert payload["data_points"] == {"GLYC": {"value": 0.95, "unit": "g/L", "status": "N"}}

    item = order.items[0]
    assert item.status == "resulted"
    assert item.result_id is not None
    assert item.csa_pushed_at is not None


def test_idempotent(db):
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC")

    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 1
    # Deuxième passage : l'item est marqué -> plus rien à pousser.
    assert push_results(db, client)["pushed"] == 0
    assert len(client.pushed) == 1


def test_not_pushed_when_result_not_releasable(db):
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC", is_validated=False)  # ni validé ni libéré

    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 0
    assert order.items[0].csa_pushed_at is None


def test_released_without_validation_is_pushed(db):
    import datetime as dt

    order = _order_with_sample(db)
    _validated_result(
        db, order.sample_id, "GLYC", is_validated=False, released_at=dt.datetime(2026, 8, 1, 9)
    )
    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 1


# ── validation vs libération en mode dégradé (§10.4) ────────────────────────
# `REQUIRE_VALIDATION_FOR_RELEASE=False` autorise la libération d'un résultat
# sans validation biologique. Ce mode ne doit JAMAIS être présenté au
# prescripteur comme une validation biologique.


def test_biological_validation_is_reported_as_such(db):
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC", is_validated=True)

    client = _FakeClient()
    push_results(db, client)
    _, _, payload = client.pushed[0]

    assert payload["statut"] == "valide"
    assert payload["validation"]["niveau"] == "biologique"
    assert payload["validation"]["mode_degrade"] is False


def test_auto_validation_is_not_reported_as_biological(db):
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC", is_validated=False, is_auto_validated=True)

    client = _FakeClient()
    push_results(db, client)
    _, _, payload = client.pushed[0]

    assert payload["statut"] == "valide_auto"
    assert payload["validation"]["niveau"] == "auto"
    assert payload["validation"]["mode_degrade"] is False


def test_degraded_release_is_never_labelled_validated(db):
    """Résultat libéré SANS validation -> jamais annoncé « valide » au prescripteur."""
    import datetime as dt

    order = _order_with_sample(db)
    _validated_result(
        db,
        order.sample_id,
        "GLYC",
        is_validated=False,
        is_auto_validated=False,
        released_at=dt.datetime(2026, 8, 1, 9),
    )

    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 1
    _, _, payload = client.pushed[0]

    assert payload["statut"] == "libere_sans_validation"
    assert payload["statut"] != "valide"
    assert payload["validation"]["niveau"] == "aucune"
    assert payload["validation"]["mode_degrade"] is True
    # L'absence de validation est explicite et traçable côté prescripteur.
    assert payload["validation"]["bio_validated_at"] is None
    assert payload["validation"]["released_at"] is not None


def test_no_sample_no_push(db):
    # Ordre CSA sans échantillon prélevé : rien à remonter (pas de résultat possible).
    apply_prescription(db, _presc())
    db.commit()
    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 0


def test_unmapped_item_skipped(db):
    order = _order_with_sample(db, examens=[{"code": "BGDC022", "nom": "VDRL"}])  # non mappé
    # Un résultat existe sur l'échantillon mais l'item est « CSA:... » : jamais poussé.
    _validated_result(db, order.sample_id, "CSA:BGDC022")
    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 0


def test_non_csa_order_ignored(db):
    # Ordre interne RuggyLab (pas d'origine CSA) : jamais remonté.
    order = _order_with_sample(db)
    order.csa_prescription_id = None
    db.commit()
    _validated_result(db, order.sample_id, "GLYC")
    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 0


def test_push_failure_leaves_item_unmarked(db):
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC")
    client = _FakeClient(fail=True)  # CSA indisponible

    assert push_results(db, client)["pushed"] == 0
    # Non marqué -> sera réessayé au prochain cycle (résilience).
    assert order.items[0].csa_pushed_at is None

    # CSA revient : le cycle suivant pousse.
    ok = _FakeClient()
    assert push_results(db, ok)["pushed"] == 1


# ── cohérence patient (§10.1) ───────────────────────────────────────────────
# Le flux sortant publie un résultat sous une identité chez un tiers. Il ne doit
# jamais le faire si l'échantillon d'où provient le résultat n'appartient pas au
# patient de l'ordre — quelle que soit la façon dont l'incohérence est apparue.


def test_result_of_another_patient_is_never_published(db):
    """Échantillon rattaché appartenant à un AUTRE patient -> publication bloquée."""
    order = _order_with_sample(db)
    # Second patient, avec son propre échantillon et son propre résultat.
    other = apply_prescription(
        db,
        _presc(prescription_id="LAB-2", dossier_no="CSA-0002", patient_nom="KONE Awa"),
    )
    db.flush()
    other_sample = Sample(barcode="B-OTHER", patient_id=other.patient_id, status="received")
    db.add(other_sample)
    db.flush()
    assert other.patient_id != order.patient_id
    _validated_result(db, other_sample.id, "GLYC")

    # Contournement de l'API : l'ordre du patient A pointe l'échantillon du patient B.
    order.sample_id = other_sample.id
    db.commit()

    client = _FakeClient()
    res = push_results(db, client)

    assert res["pushed"] == 0, "un résultat d'un autre patient ne doit jamais être publié"
    assert client.pushed == []
    assert order.items[0].csa_pushed_at is None
    assert order.items[0].result_id is None


def test_orphan_sample_reference_blocks_publication(db):
    """Échantillon référencé mais introuvable -> fail-closed, aucune publication."""
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC")
    order.sample_id = 999999  # référence orpheline
    db.commit()

    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 0
    assert client.pushed == []


def test_patient_swap_after_order_creation_blocks_publication(db):
    """Le patient de l'ordre change après coup -> l'échantillon ne correspond plus."""
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC")
    other = apply_prescription(
        db,
        _presc(prescription_id="LAB-3", dossier_no="CSA-0003", patient_nom="TRAORE Ali"),
    )
    db.flush()
    order.patient_id = other.patient_id  # bascule silencieuse d'identité
    db.commit()

    client = _FakeClient()
    assert push_results(db, client)["pushed"] == 0
    assert client.pushed == []


def test_health_report_also_ignores_cross_patient_item(db):
    """Le monitoring partage le même garde-fou : pas de faux « prêt à pousser »."""
    from app.services.csa_sync.health import sync_health

    order = _order_with_sample(db)
    other = apply_prescription(
        db,
        _presc(prescription_id="LAB-4", dossier_no="CSA-0004", patient_nom="BAMBA Sita"),
    )
    db.flush()
    other_sample = Sample(barcode="B-OTHER-2", patient_id=other.patient_id, status="received")
    db.add(other_sample)
    db.flush()
    _validated_result(db, other_sample.id, "GLYC")
    order.sample_id = other_sample.id
    db.commit()

    health = sync_health(db)
    assert health["outbound"]["pending_total"] == 1  # l'item est bien éligible…
    assert health["outbound"]["pending_ready"] == 0  # …mais jamais « prêt à pousser »


# ── idempotence sous rejeu / concurrence (§10.2) ────────────────────────────


def test_replay_never_duplicates_even_across_cycles(db):
    """Trois cycles consécutifs : un seul événement émis pour le même item."""
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC")

    client = _FakeClient()
    totals = [push_results(db, client)["pushed"] for _ in range(3)]

    assert totals == [1, 0, 0]
    assert len(client.pushed) == 1
    assert len({sid for _, sid, _ in client.pushed}) == 1


def test_concurrent_cycles_do_not_release_twice(db):
    """Deux sessions concurrentes sur la même base : un seul push effectif.

    Simule deux workers sortants menés en parallèle sur le même item. Le second
    ne doit ni republier, ni écraser l'horodatage d'idempotence du premier.
    """
    order = _order_with_sample(db)
    _validated_result(db, order.sample_id, "GLYC")

    second = db_session.SessionLocal()
    try:
        first_client, second_client = _FakeClient(), _FakeClient()
        first = push_results(db, first_client)["pushed"]
        # La seconde session lit l'état déjà commité par la première.
        concurrent = push_results(second, second_client)["pushed"]
    finally:
        second.close()

    assert first == 1
    assert concurrent == 0
    assert len(first_client.pushed) + len(second_client.pushed) == 1
