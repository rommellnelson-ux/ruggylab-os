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
