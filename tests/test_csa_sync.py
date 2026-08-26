"""Tests du flux entrant d'intégration CSA (phase I1)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from pathlib import Path

import pytest

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.models import ExamOrder, Patient
from app.services.csa_sync import exam_map
from app.services.csa_sync.inbound import apply_prescription, poll_once


@pytest.fixture()
def db(tmp_path: Path) -> Generator[db_session.Session, None, None]:
    settings.TESTING = True
    db_session.configure_database(f"sqlite:///{tmp_path / 'csa_sync.db'}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)
    session = db_session.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=db_session.engine)


def _presc(**over) -> dict:
    base = {
        "prescription_id": "LAB-1",
        "dossier_no": "CSA-0001",
        "patient_nom": "DIOMANDE Kenza",
        "date_naissance": "1990-06-15",
        "sexe": "F",
        "priorite": "urgent",
        "origine": "clinique",
        "motif": "Fièvre",
        "prescripteur_nom": "Dr Test",
        "examens": [{"code": "BEDA005", "nom": "NFS"}, {"code": "BNDA008", "nom": "Glycémie"}],
    }
    base.update(over)
    return base


# ── exam_map ──────────────────────────────────────────────────────────────
def test_map_simple():
    assert exam_map.map_exam("BEDA005") == ["NFS"]
    assert exam_map.map_exam("bnda008") == ["GLYC"]  # insensible à la casse


def test_map_bundle_1_to_n():
    assert exam_map.map_exam("BNDB005") == ["CHOL", "TG", "HDL", "LDL"]
    assert exam_map.map_exam("BNDA014") == ["UREE", "CREAT"]


def test_map_unmapped():
    assert exam_map.map_exam("TEZZ001") == []  # acte de soin, pas un examen labo
    assert exam_map.map_exam("") == []
    assert exam_map.is_mapped("BEDA005") is True


# ── apply_prescription ────────────────────────────────────────────────────
def test_creates_patient_and_order(db):
    order = apply_prescription(db, _presc())
    db.commit()
    assert order.csa_prescription_id == "LAB-1"
    assert order.priority == "urgent"
    patient = db.get(Patient, order.patient_id)
    assert patient.ipp_unique_id == "CSA-CSA-0001"
    assert patient.last_name == "DIOMANDE" and patient.first_name == "Kenza"
    assert patient.birth_date == dt.date(1990, 6, 15)
    assert patient.birth_date_estimee is False
    assert patient.sex == "F"
    codes = sorted(i.exam_code for i in order.items)
    assert codes == ["GLYC", "NFS"]
    assert all(i.status == "pending" for i in order.items)


def test_sentinel_dob_when_missing(db):
    order = apply_prescription(db, _presc(date_naissance=""))
    db.commit()
    patient = db.get(Patient, order.patient_id)
    assert patient.birth_date == dt.date(1900, 1, 1)
    assert patient.birth_date_estimee is True


def test_unmapped_exam_is_preserved(db):
    order = apply_prescription(db, _presc(examens=[{"code": "BGDC022", "nom": "VDRL (syphilis)"}]))
    db.commit()
    assert len(order.items) == 1
    item = order.items[0]
    assert item.status == "unmapped"
    assert item.exam_code == "CSA:BGDC022"
    assert item.exam_label == "VDRL (syphilis)"


def test_idempotent(db):
    o1 = apply_prescription(db, _presc())
    db.commit()
    o2 = apply_prescription(db, _presc(motif="autre"))  # même prescription_id
    db.commit()
    assert o1.id == o2.id
    assert db.query(ExamOrder).count() == 1


def test_dob_completed_later(db):
    apply_prescription(db, _presc(date_naissance=""))  # sentinelle
    db.commit()
    # Une nouvelle prescription du même patient avec une vraie DDN la complète.
    apply_prescription(db, _presc(prescription_id="LAB-2", date_naissance="1990-06-15"))
    db.commit()
    patient = db.query(Patient).filter_by(ipp_unique_id="CSA-CSA-0001").one()
    assert patient.birth_date == dt.date(1990, 6, 15)
    assert patient.birth_date_estimee is False


# ── poll_once avec client simulé ──────────────────────────────────────────
class _FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.pushed: list = []

    def pull_prescriptions(self, changed_since, max_rows):
        return [r for r in self.rows if r["updated_at"] > changed_since]

    def push_event(self, kind, source_item_id, payload):
        self.pushed.append((kind, source_item_id, payload))
        return f"{kind}:{source_item_id}"


def test_poll_advances_watermark_and_acks(db):
    rows = [
        {"updated_at": "2026-08-01T10:00:00+00:00", "payload": _presc(prescription_id="LAB-1")},
        {"updated_at": "2026-08-01T11:00:00+00:00", "payload": _presc(prescription_id="LAB-2")},
    ]
    client = _FakeClient(rows)
    res = poll_once(db, client)
    assert res["processed"] == 2
    assert res["watermark"] == "2026-08-01T11:00:00+00:00"
    assert db.query(ExamOrder).count() == 2
    assert [k for k, _, _ in client.pushed] == ["labo_receipts", "labo_receipts"]

    # Re-poll : le watermark filtre tout, rien n'est retraité.
    res2 = poll_once(db, client)
    assert res2["processed"] == 0
    assert db.query(ExamOrder).count() == 2
