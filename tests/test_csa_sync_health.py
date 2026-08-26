"""Tests de l'observabilité de l'intégration CSA (phase I4)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.models import Result, Sample
from app.services.csa_sync.health import sync_health, unmapped_report
from app.services.csa_sync.inbound import apply_prescription
from app.services.csa_sync.outbound import push_results


@pytest.fixture()
def db(tmp_path: Path) -> Generator[db_session.Session, None, None]:
    settings.TESTING = True
    db_session.configure_database(f"sqlite:///{tmp_path / 'csa_health.db'}")
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
        self.fail = fail

    def push_event(self, kind, source_item_id, payload):
        if self.fail:
            raise RuntimeError("CSA indisponible")
        return f"{kind}:{source_item_id}"


def _presc(**over) -> dict:
    base = {
        "prescription_id": "LAB-1",
        "dossier_no": "CSA-0001",
        "patient_nom": "DIOMANDE Kenza",
        "examens": [{"code": "BNDA008", "nom": "Glycémie"}],  # -> GLYC
    }
    base.update(over)
    return base


def _order_with_sample_result(db):
    order = apply_prescription(db, _presc())
    db.flush()
    sample = Sample(barcode=f"B-{order.id}", patient_id=order.patient_id, status="received")
    db.add(sample)
    db.flush()
    order.sample_id = sample.id
    db.add(Result(
        sample_id=sample.id, exam_code="GLYC",
        data_points={"GLYC": {"value": 0.9}}, is_validated=True,
    ))
    db.commit()
    return order


def test_health_empty(db):
    h = sync_health(db)
    assert h["healthy"] is True
    assert h["inbound"]["processed_count"] == 0
    assert h["outbound"]["pushed_count"] == 0
    assert h["outbound"]["pending_total"] == 0
    assert h["unmapped_exams"] == []


def test_unmapped_report(db):
    apply_prescription(db, _presc(examens=[
        {"code": "BGDC022", "nom": "VDRL"},
        {"code": "BGDC022", "nom": "VDRL"},  # même code -> agrégé
        {"code": "BZZZ999", "nom": "Exotique"},
    ]))
    db.commit()
    rep = unmapped_report(db)
    codes = {r["code"]: r["count"] for r in rep}
    assert codes["CSA:BGDC022"] == 2
    assert codes["CSA:BZZZ999"] == 1
    # Trié par fréquence décroissante.
    assert rep[0]["code"] == "CSA:BGDC022"


def test_health_pending_then_pushed(db):
    _order_with_sample_result(db)
    h = sync_health(db)
    assert h["outbound"]["pending_total"] == 1
    assert h["outbound"]["pending_ready"] == 1
    assert h["orders"]["csa_orders_total"] == 1
    assert h["orders"]["items_pushed_total"] == 0

    push_results(db, _FakeClient())
    h2 = sync_health(db)
    assert h2["outbound"]["pending_ready"] == 0
    assert h2["outbound"]["pushed_count"] == 1
    assert h2["orders"]["items_pushed_total"] == 1
    assert h2["healthy"] is True


def test_health_records_outbound_error(db):
    _order_with_sample_result(db)
    push_results(db, _FakeClient(fail=True))  # échec réseau -> erreur tracée
    h = sync_health(db)
    assert h["outbound"]["last_error"] is not None
    assert h["healthy"] is False
    # L'item reste en attente (non marqué), donc réessayable.
    assert h["outbound"]["pending_ready"] == 1
