"""Preuves PostgreSQL de sérialisation des encaissements synthétiques."""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import bnpl as bnpl_endpoint
from app.api.v1.endpoints import invoices as invoices_endpoint
from app.api.v1.endpoints.bnpl import record_payment as record_bnpl_payment
from app.api.v1.endpoints.invoices import record_payment
from app.db.session import SessionLocal, engine
from app.models import AuditEvent, Invoice, InvoicePayment, User, UserRole
from app.models.bnpl import BNPLPayment, BNPLSchedule
from app.schemas.bnpl import BNPLPaymentCreate, BNPLScheduleCreate
from app.schemas.invoice import PaymentCreate
from app.services.bnpl_tracker import BNPLTracker

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ce test valide les verrous de facturation sous PostgreSQL.",
)


def test_concurrent_invoice_payments_preserve_their_sum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        user = User(
            username=f"finance_pg_{suffix}",
            hashed_password="synthetic-not-used",
            role=UserRole.ADMIN,
            is_active=True,
        )
        setup.add(user)
        setup.flush()
        invoice = Invoice(
            invoice_number=f"FACT-SYN-{suffix}",
            patient_type="UNINSURED",
            gross_total_xof=Decimal("10000"),
            discount_xof=Decimal("0"),
            net_total_xof=Decimal("10000"),
            cnam_part_xof=Decimal("0"),
            patient_due_xof=Decimal("10000"),
            paid_xof=Decimal("0"),
            status="issued",
            created_by_id=user.id,
        )
        setup.add(invoice)
        setup.commit()
        user_id = user.id
        invoice_id = invoice.id

    first_payment_holds_lock = threading.Event()
    release_first_payment = threading.Event()
    original_log_audit_event = invoices_endpoint.log_audit_event

    def pause_first_payment(*args: Any, **kwargs: Any) -> AuditEvent:
        payload = kwargs.get("payload")
        if (
            kwargs.get("event_type") == "invoice.payment.record"
            and isinstance(payload, dict)
            and payload.get("amount_xof") == "3000"
        ):
            first_payment_holds_lock.set()
            assert release_first_payment.wait(timeout=5)
        return original_log_audit_event(*args, **kwargs)

    monkeypatch.setattr(invoices_endpoint, "log_audit_event", pause_first_payment)

    def pay(amount: str) -> Decimal:
        with SessionLocal() as db:
            current_user = db.get(User, user_id)
            assert current_user is not None
            result = record_payment(
                invoice_id,
                PaymentCreate(amount_xof=Decimal(amount), method="CASH"),
                db,
                current_user,
            )
            return result.paid_xof

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        first = executor.submit(pay, "3000")
        assert first_payment_holds_lock.wait(timeout=5)
        second = executor.submit(pay, "4000")
        time.sleep(0.25)
        assert not second.done(), "le second encaissement n'a pas attendu le verrou facture"

        release_first_payment.set()
        assert first.result(timeout=10) == Decimal("3000")
        assert second.result(timeout=10) == Decimal("7000")

        with SessionLocal() as verification:
            invoice = verification.get(Invoice, invoice_id)
            assert invoice is not None
            payments = (
                verification.query(InvoicePayment)
                .filter(InvoicePayment.invoice_id == invoice_id)
                .all()
            )
            events = (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "invoice.payment.record",
                    AuditEvent.entity_id == str(invoice_id),
                )
                .order_by(AuditEvent.id.asc())
                .all()
            )
            assert invoice.paid_xof == Decimal("7000")
            assert sum((payment.amount_xof for payment in payments), Decimal("0")) == Decimal(
                "7000"
            )
            assert [json.loads(event.payload or "{}")["amount_xof"] for event in events] == [
                "3000",
                "4000",
            ]
    finally:
        release_first_payment.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.entity_type == "invoice",
                AuditEvent.entity_id == str(invoice_id),
            ).delete(synchronize_session=False)
            cleanup.query(InvoicePayment).filter(InvoicePayment.invoice_id == invoice_id).delete(
                synchronize_session=False
            )
            stored_invoice = cleanup.get(Invoice, invoice_id)
            if stored_invoice is not None:
                cleanup.delete(stored_invoice)
            stored_user = cleanup.get(User, user_id)
            if stored_user is not None:
                cleanup.delete(stored_user)
            cleanup.commit()


def test_concurrent_duplicate_bnpl_payment_is_recorded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        user = User(
            username=f"bnpl_pg_{suffix}",
            hashed_password="synthetic-not-used",
            role=UserRole.ADMIN,
            is_active=True,
        )
        setup.add(user)
        setup.flush()
        schedule = BNPLTracker().create_schedule(
            setup,
            BNPLScheduleCreate(
                patient_ref=f"SYNTHETIC-{suffix}",
                total_amount_xof=10000,
                installment_months=2,
            ),
        )
        invoice = Invoice(
            invoice_number=f"FACT-BNPL-SYN-{suffix}",
            patient_type="UNINSURED",
            gross_total_xof=Decimal("10000"),
            discount_xof=Decimal("0"),
            net_total_xof=Decimal("10000"),
            cnam_part_xof=Decimal("0"),
            patient_due_xof=Decimal("10000"),
            paid_xof=Decimal("0"),
            status="issued",
            created_by_id=user.id,
            payment_plan_id=schedule.id,
        )
        setup.add(invoice)
        setup.commit()
        user_id = user.id
        schedule_id = schedule.id
        invoice_id = invoice.id

    first_payment_holds_lock = threading.Event()
    release_first_payment = threading.Event()
    original_log_audit_event = bnpl_endpoint.log_audit_event

    def pause_first_payment(*args: Any, **kwargs: Any) -> AuditEvent:
        if kwargs.get("event_type") == "bnpl.payment.record":
            first_payment_holds_lock.set()
            assert release_first_payment.wait(timeout=5)
        return original_log_audit_event(*args, **kwargs)

    monkeypatch.setattr(bnpl_endpoint, "log_audit_event", pause_first_payment)

    def pay() -> str:
        with SessionLocal() as db:
            current_user = db.get(User, user_id)
            assert current_user is not None
            result = record_bnpl_payment(
                schedule_id,
                BNPLPaymentCreate(
                    schedule_id=schedule_id,
                    installment_number=1,
                    amount_xof=5000,
                ),
                db,
                current_user,
            )
            return result.status

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        first = executor.submit(pay)
        assert first_payment_holds_lock.wait(timeout=5)
        duplicate = executor.submit(pay)
        time.sleep(0.25)
        assert not duplicate.done(), "le rejeu BNPL n'a pas attendu le verrou du plan"

        release_first_payment.set()
        assert first.result(timeout=10) == "PAID"
        with pytest.raises(HTTPException) as duplicate_error:
            duplicate.result(timeout=10)
        assert duplicate_error.value.status_code == 409

        with SessionLocal() as verification:
            invoice = verification.get(Invoice, invoice_id)
            installment = (
                verification.query(BNPLPayment)
                .filter(
                    BNPLPayment.schedule_id == schedule_id,
                    BNPLPayment.installment_number == 1,
                )
                .one()
            )
            assert invoice is not None
            assert installment.status == "PAID"
            assert invoice.paid_xof == Decimal("5000")
            assert (
                verification.query(InvoicePayment)
                .filter(InvoicePayment.invoice_id == invoice_id)
                .count()
                == 1
            )
            assert (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "bnpl.payment.record",
                    AuditEvent.user_id == user_id,
                )
                .count()
                == 1
            )
    finally:
        release_first_payment.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "bnpl.payment.record",
                AuditEvent.user_id == user_id,
            ).delete(synchronize_session=False)
            cleanup.query(InvoicePayment).filter(InvoicePayment.invoice_id == invoice_id).delete(
                synchronize_session=False
            )
            stored_invoice = cleanup.get(Invoice, invoice_id)
            if stored_invoice is not None:
                cleanup.delete(stored_invoice)
            cleanup.query(BNPLPayment).filter(BNPLPayment.schedule_id == schedule_id).delete(
                synchronize_session=False
            )
            stored_schedule = cleanup.get(BNPLSchedule, schedule_id)
            if stored_schedule is not None:
                cleanup.delete(stored_schedule)
            stored_user = cleanup.get(User, user_id)
            if stored_user is not None:
                cleanup.delete(stored_user)
            cleanup.commit()
