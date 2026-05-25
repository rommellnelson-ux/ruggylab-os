"""
Tests du module BNPL (Buy Now Pay Later / micro-crédit santé CMU)
=================================================================

Couverture :
  - Création d'un plan → N échéances PENDING générées
  - Somme des échéances = total_amount_xof (±1 XOF pour arrondis)
  - Enregistrement d'un paiement → statut PAID
  - Plan avec tous paiements PAID → plan status = COMPLETED
  - get_summary : paid/remaining/overdue corrects
  - get_overdue : retourne seulement les plans avec due_date passée
  - Validation Pydantic : installment_months < 2 → erreur
  - Test du endpoint FastAPI via TestClient (SQLite in-memory via fixture conftest)
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.main import create_app
from app.schemas.bnpl import BNPLScheduleCreate
from app.services.bnpl_tracker import BNPLTracker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Generator[Session, None, None]:
    """Session SQLAlchemy SQLite in-memory isolée pour les tests unitaires."""
    db_url = f"sqlite:///{tmp_path}/test_bnpl.db"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    _SessionLocal = sessionmaker(autoflush=False, autocommit=False, bind=engine)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def tracker() -> BNPLTracker:
    return BNPLTracker()


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """TestClient FastAPI avec SQLite in-memory et admin seedé."""
    database_path = tmp_path / "test_bnpl_api.db"
    settings.TESTING = True
    settings.ENABLE_DH36_LISTENER = False
    settings.SECRET_KEY = "test_secret_key_bnpl_only_123456"
    settings.FIRST_SUPERUSER = "admin"
    settings.FIRST_SUPERUSER_PASSWORD = "admin_bnpl_pass"
    settings.FIRST_SUPERUSER_FULL_NAME = "BNPL Test Admin"
    db_session.configure_database(f"sqlite:///{database_path}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)

    from app.services.bootstrap import init_db
    init_db()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=db_session.engine)


def _auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "admin_bnpl_pass"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_data(
    patient_ref: str = "CNAM-CI-2026-001",
    total_amount_xof: int = 6000,
    installment_months: int = 3,
    prescriber_id: str | None = "DR-KONAN",
) -> BNPLScheduleCreate:
    return BNPLScheduleCreate(
        patient_ref=patient_ref,
        total_amount_xof=total_amount_xof,
        installment_months=installment_months,
        prescriber_id=prescriber_id,
    )


# ---------------------------------------------------------------------------
# Tests unitaires — BNPLTracker
# ---------------------------------------------------------------------------


class TestCreateSchedule:
    def test_creates_n_payments(self, tracker: BNPLTracker, db: Session) -> None:
        data = _create_data(installment_months=3)
        result = tracker.create_schedule(db, data)
        assert result.id is not None
        assert len(result.payments) == 3

    def test_all_payments_pending(self, tracker: BNPLTracker, db: Session) -> None:
        data = _create_data(installment_months=4)
        result = tracker.create_schedule(db, data)
        statuses = {p.status for p in result.payments}
        assert statuses == {"PENDING"}

    def test_payment_sum_equals_total(self, tracker: BNPLTracker, db: Session) -> None:
        """Somme des échéances = total_amount_xof (±1 XOF pour arrondis)."""
        data = _create_data(total_amount_xof=10000, installment_months=3)
        result = tracker.create_schedule(db, data)
        total = sum(p.amount_xof for p in result.payments)
        assert abs(total - data.total_amount_xof) <= 1

    def test_payment_sum_exact_divisible(self, tracker: BNPLTracker, db: Session) -> None:
        """Somme exacte quand total est divisible par N."""
        data = _create_data(total_amount_xof=6000, installment_months=3)
        result = tracker.create_schedule(db, data)
        total = sum(p.amount_xof for p in result.payments)
        assert total == 6000

    def test_payment_sum_with_remainder(self, tracker: BNPLTracker, db: Session) -> None:
        """Somme exacte même avec un reste d'arrondi."""
        data = _create_data(total_amount_xof=10001, installment_months=3)
        result = tracker.create_schedule(db, data)
        total = sum(p.amount_xof for p in result.payments)
        assert total == 10001

    def test_due_dates_are_future(self, tracker: BNPLTracker, db: Session) -> None:
        data = _create_data(installment_months=3)
        result = tracker.create_schedule(db, data)
        today = dt.date.today()
        for p in result.payments:
            assert p.due_date > today

    def test_installment_numbers_sequential(self, tracker: BNPLTracker, db: Session) -> None:
        data = _create_data(installment_months=5)
        result = tracker.create_schedule(db, data)
        numbers = [p.installment_number for p in result.payments]
        assert numbers == list(range(1, 6))

    def test_schedule_status_active(self, tracker: BNPLTracker, db: Session) -> None:
        data = _create_data()
        result = tracker.create_schedule(db, data)
        assert result.status == "ACTIVE"

    def test_prescriber_id_stored(self, tracker: BNPLTracker, db: Session) -> None:
        data = _create_data(prescriber_id="DR-YAPI")
        result = tracker.create_schedule(db, data)
        # Vérifier via la base
        from app.models.bnpl import BNPLSchedule
        schedule = db.get(BNPLSchedule, result.id)
        assert schedule is not None
        assert schedule.prescriber_id == "DR-YAPI"

    def test_prescriber_id_optional(self, tracker: BNPLTracker, db: Session) -> None:
        data = _create_data(prescriber_id=None)
        result = tracker.create_schedule(db, data)
        assert result.id is not None


class TestRecordPayment:
    def test_payment_marked_paid(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(installment_months=3))
        payment = tracker.record_payment(db, schedule.id, 1, 2000)
        assert payment.status == "PAID"
        assert payment.paid_at is not None

    def test_payment_amount_updated(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(total_amount_xof=6000, installment_months=3))
        payment = tracker.record_payment(db, schedule.id, 1, 1999)
        assert payment.amount_xof == 1999

    def test_plan_remains_active_partial(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(installment_months=3))
        tracker.record_payment(db, schedule.id, 1, 2000)
        from app.models.bnpl import BNPLSchedule
        s = db.get(BNPLSchedule, schedule.id)
        assert s is not None
        assert s.status == "ACTIVE"

    def test_plan_completed_when_all_paid(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(total_amount_xof=6000, installment_months=3))
        tracker.record_payment(db, schedule.id, 1, 2000)
        tracker.record_payment(db, schedule.id, 2, 2000)
        tracker.record_payment(db, schedule.id, 3, 2000)
        from app.models.bnpl import BNPLSchedule
        s = db.get(BNPLSchedule, schedule.id)
        assert s is not None
        assert s.status == "COMPLETED"

    def test_duplicate_payment_raises_409(self, tracker: BNPLTracker, db: Session) -> None:
        from fastapi import HTTPException
        schedule = tracker.create_schedule(db, _create_data(installment_months=2))
        tracker.record_payment(db, schedule.id, 1, 1000)
        with pytest.raises(HTTPException) as exc_info:
            tracker.record_payment(db, schedule.id, 1, 1000)
        assert exc_info.value.status_code == 409

    def test_unknown_schedule_raises_404(self, tracker: BNPLTracker, db: Session) -> None:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            tracker.record_payment(db, 9999, 1, 1000)
        assert exc_info.value.status_code == 404

    def test_unknown_installment_raises_404(self, tracker: BNPLTracker, db: Session) -> None:
        from fastapi import HTTPException
        schedule = tracker.create_schedule(db, _create_data(installment_months=2))
        with pytest.raises(HTTPException) as exc_info:
            tracker.record_payment(db, schedule.id, 99, 1000)
        assert exc_info.value.status_code == 404


class TestGetSummary:
    def test_initial_summary(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(total_amount_xof=6000, installment_months=3))
        summary = tracker.get_summary(db, schedule.id)
        assert summary.paid_amount_xof == 0
        assert summary.remaining_xof == 6000
        assert summary.overdue_count == 0

    def test_summary_after_payment(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(total_amount_xof=6000, installment_months=3))
        tracker.record_payment(db, schedule.id, 1, 2000)
        summary = tracker.get_summary(db, schedule.id)
        assert summary.paid_amount_xof == 2000
        assert summary.remaining_xof == 4000

    def test_summary_overdue_count(self, tracker: BNPLTracker, db: Session) -> None:
        """Overdue count = 0 par défaut (due_dates dans le futur)."""
        schedule = tracker.create_schedule(db, _create_data(installment_months=3))
        summary = tracker.get_summary(db, schedule.id)
        assert summary.overdue_count == 0

    def test_summary_overdue_count_with_past_due(self, tracker: BNPLTracker, db: Session) -> None:
        """Simule des échéances avec due_date dans le passé."""
        schedule = tracker.create_schedule(db, _create_data(installment_months=3))
        # Modifier manuellement la due_date d'une échéance pour la mettre dans le passé
        from app.models.bnpl import BNPLPayment
        payment = (
            db.query(BNPLPayment)
            .filter(
                BNPLPayment.schedule_id == schedule.id,
                BNPLPayment.installment_number == 1,
            )
            .first()
        )
        assert payment is not None
        payment.due_date = dt.date.today() - dt.timedelta(days=1)
        db.commit()

        summary = tracker.get_summary(db, schedule.id)
        assert summary.overdue_count == 1

    def test_summary_unknown_schedule_raises_404(self, tracker: BNPLTracker, db: Session) -> None:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            tracker.get_summary(db, 9999)
        assert exc_info.value.status_code == 404

    def test_summary_patient_ref(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(patient_ref="PATIENT-XYZ"))
        summary = tracker.get_summary(db, schedule.id)
        assert summary.patient_ref == "PATIENT-XYZ"


class TestGetOverdue:
    def test_no_overdue_initially(self, tracker: BNPLTracker, db: Session) -> None:
        tracker.create_schedule(db, _create_data(installment_months=3))
        overdue = tracker.get_overdue(db)
        assert overdue == []

    def test_returns_overdue_plans(self, tracker: BNPLTracker, db: Session) -> None:
        schedule = tracker.create_schedule(db, _create_data(installment_months=2))
        # Forcer une due_date dans le passé
        from app.models.bnpl import BNPLPayment
        payment = (
            db.query(BNPLPayment)
            .filter(
                BNPLPayment.schedule_id == schedule.id,
                BNPLPayment.installment_number == 1,
            )
            .first()
        )
        assert payment is not None
        payment.due_date = dt.date.today() - dt.timedelta(days=5)
        db.commit()

        overdue = tracker.get_overdue(db)
        assert len(overdue) == 1
        assert overdue[0].schedule_id == schedule.id

    def test_paid_overdue_not_returned(self, tracker: BNPLTracker, db: Session) -> None:
        """Un plan dont l'échéance en retard a été payée ne doit pas apparaître."""
        schedule = tracker.create_schedule(db, _create_data(installment_months=2))
        from app.models.bnpl import BNPLPayment
        payment = (
            db.query(BNPLPayment)
            .filter(
                BNPLPayment.schedule_id == schedule.id,
                BNPLPayment.installment_number == 1,
            )
            .first()
        )
        assert payment is not None
        payment.due_date = dt.date.today() - dt.timedelta(days=5)
        db.commit()

        # Maintenant payer cette échéance
        tracker.record_payment(db, schedule.id, 1, 3000)
        overdue = tracker.get_overdue(db)
        assert overdue == []

    def test_multiple_overdue_plans(self, tracker: BNPLTracker, db: Session) -> None:
        s1 = tracker.create_schedule(db, _create_data(patient_ref="P1", installment_months=2))
        s2 = tracker.create_schedule(db, _create_data(patient_ref="P2", installment_months=2))
        # Plan 3 sans retard
        tracker.create_schedule(db, _create_data(patient_ref="P3", installment_months=2))

        from app.models.bnpl import BNPLPayment
        for sid in (s1.id, s2.id):
            p = (
                db.query(BNPLPayment)
                .filter(BNPLPayment.schedule_id == sid, BNPLPayment.installment_number == 1)
                .first()
            )
            assert p is not None
            p.due_date = dt.date.today() - dt.timedelta(days=3)
        db.commit()

        overdue = tracker.get_overdue(db)
        overdue_ids = {o.schedule_id for o in overdue}
        assert s1.id in overdue_ids
        assert s2.id in overdue_ids
        assert len(overdue) == 2


# ---------------------------------------------------------------------------
# Validation Pydantic
# ---------------------------------------------------------------------------


class TestPydanticValidation:
    def test_installment_months_lt_2_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            BNPLScheduleCreate(
                patient_ref="TEST",
                total_amount_xof=1000,
                installment_months=1,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("installment_months",) for e in errors)

    def test_installment_months_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            BNPLScheduleCreate(
                patient_ref="TEST",
                total_amount_xof=1000,
                installment_months=0,
            )

    def test_total_amount_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            BNPLScheduleCreate(
                patient_ref="TEST",
                total_amount_xof=0,
                installment_months=2,
            )

    def test_total_amount_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            BNPLScheduleCreate(
                patient_ref="TEST",
                total_amount_xof=-500,
                installment_months=2,
            )

    def test_empty_patient_ref_raises(self) -> None:
        with pytest.raises(ValidationError):
            BNPLScheduleCreate(
                patient_ref="",
                total_amount_xof=1000,
                installment_months=2,
            )

    def test_valid_data_no_error(self) -> None:
        data = BNPLScheduleCreate(
            patient_ref="CNAM-2026-001",
            total_amount_xof=12000,
            installment_months=6,
            prescriber_id="DR-BAMBA",
        )
        assert data.installment_months == 6

    def test_installment_months_24_valid(self) -> None:
        data = BNPLScheduleCreate(
            patient_ref="CNAM-2026-001",
            total_amount_xof=12000,
            installment_months=24,
        )
        assert data.installment_months == 24

    def test_installment_months_25_raises(self) -> None:
        with pytest.raises(ValidationError):
            BNPLScheduleCreate(
                patient_ref="CNAM-2026-001",
                total_amount_xof=12000,
                installment_months=25,
            )


# ---------------------------------------------------------------------------
# Tests d'intégration — Endpoints FastAPI
# ---------------------------------------------------------------------------


class TestBNPLEndpoints:
    def test_create_schedule_endpoint(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.post(
            "/api/v1/billing/bnpl/schedule",
            headers=headers,
            json={
                "patient_ref": "CNAM-CI-2026-001",
                "total_amount_xof": 6000,
                "installment_months": 3,
                "prescriber_id": "DR-TEST",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["id"] is not None
        assert data["status"] == "ACTIVE"
        assert len(data["payments"]) == 3

    def test_get_schedule_endpoint(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        create_resp = client.post(
            "/api/v1/billing/bnpl/schedule",
            headers=headers,
            json={
                "patient_ref": "PATIENT-A",
                "total_amount_xof": 4000,
                "installment_months": 2,
            },
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/billing/bnpl/schedule/{schedule_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == schedule_id
        assert len(data["payments"]) == 2

    def test_get_schedule_not_found(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.get("/api/v1/billing/bnpl/schedule/9999", headers=headers)
        assert resp.status_code == 404

    def test_record_payment_endpoint(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        create_resp = client.post(
            "/api/v1/billing/bnpl/schedule",
            headers=headers,
            json={
                "patient_ref": "PATIENT-B",
                "total_amount_xof": 4000,
                "installment_months": 2,
            },
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["id"]

        pay_resp = client.post(
            f"/api/v1/billing/bnpl/schedule/{schedule_id}/pay",
            headers=headers,
            json={
                "schedule_id": schedule_id,
                "installment_number": 1,
                "amount_xof": 2000,
            },
        )
        assert pay_resp.status_code == 200, pay_resp.text
        payment = pay_resp.json()
        assert payment["status"] == "PAID"

    def test_get_summary_endpoint(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        create_resp = client.post(
            "/api/v1/billing/bnpl/schedule",
            headers=headers,
            json={
                "patient_ref": "PATIENT-C",
                "total_amount_xof": 6000,
                "installment_months": 3,
            },
        )
        schedule_id = create_resp.json()["id"]
        client.post(
            f"/api/v1/billing/bnpl/schedule/{schedule_id}/pay",
            headers=headers,
            json={"schedule_id": schedule_id, "installment_number": 1, "amount_xof": 2000},
        )

        resp = client.get(f"/api/v1/billing/bnpl/summary/{schedule_id}", headers=headers)
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["paid_amount_xof"] == 2000
        assert summary["remaining_xof"] == 4000
        assert summary["overdue_count"] == 0

    def test_overdue_endpoint_empty(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.get("/api/v1/billing/bnpl/overdue", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_schedule_invalid_months(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        resp = client.post(
            "/api/v1/billing/bnpl/schedule",
            headers=headers,
            json={
                "patient_ref": "PATIENT-D",
                "total_amount_xof": 1000,
                "installment_months": 1,
            },
        )
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/v1/billing/bnpl/overdue")
        assert resp.status_code == 401
