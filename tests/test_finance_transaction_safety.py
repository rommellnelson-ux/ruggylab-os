"""Atomicité et traçabilité des mutations de facturation synthétiques."""

from __future__ import annotations

import json
import uuid
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import bnpl as bnpl_endpoint
from app.api.v1.endpoints import invoices as invoices_endpoint
from app.db.session import SessionLocal
from app.models import AuditEvent, Invoice, InvoicePayment
from app.models.bnpl import BNPLPayment


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_invoice(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/invoices",
        headers=headers,
        json={
            "patient_label": "Dossier synthétique finance",
            "patient_type": "UNINSURED",
            "lines": [
                {
                    "exam_code": "SYN",
                    "label": "Acte synthétique",
                    "quantity": 1,
                    "unit_price_xof": "10000",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _fail_audit(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("synthetic finance audit failure")


def _fail_invoice_sync(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("synthetic invoice synchronization failure")


def test_invoice_payment_is_audited_without_reference_content(client: TestClient) -> None:
    headers = _auth(client)
    invoice_id = _create_invoice(client, headers)
    reference = f"REFERENCE-SYNTHETIQUE-{uuid.uuid4().hex}"

    response = client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        headers=headers,
        json={"amount_xof": "2500", "method": "MOBILE_MONEY", "reference": reference},
    )

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "invoice.payment.record",
                AuditEvent.entity_id == str(invoice_id),
            )
            .one_or_none()
        )
        assert event is not None
        assert json.loads(event.payload or "{}") == {
            "amount_xof": "2500",
            "method": "MOBILE_MONEY",
        }
        assert reference not in (event.payload or "")


def test_invoice_payment_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    invoice_id = _create_invoice(client, headers)
    monkeypatch.setattr(invoices_endpoint, "log_audit_event", _fail_audit)

    with pytest.raises(RuntimeError, match="synthetic finance audit failure"):
        client.post(
            f"/api/v1/invoices/{invoice_id}/payments",
            headers=headers,
            json={"amount_xof": "2500", "method": "CASH"},
        )

    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_id)
        assert invoice is not None
        assert int(invoice.paid_xof) == 0
        assert invoice.status == "issued"
        assert db.query(InvoicePayment).filter(InvoicePayment.invoice_id == invoice_id).count() == 0
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "invoice.payment.record",
                AuditEvent.entity_id == str(invoice_id),
            )
            .count()
            == 0
        )


def test_cancel_plan_and_refund_emit_minimal_audit_events(client: TestClient) -> None:
    headers = _auth(client)

    cancelled_id = _create_invoice(client, headers)
    cancel_response = client.post(f"/api/v1/invoices/{cancelled_id}/cancel", headers=headers)
    assert cancel_response.status_code == 200, cancel_response.text

    planned_id = _create_invoice(client, headers)
    plan_response = client.post(
        f"/api/v1/invoices/{planned_id}/payment-plan",
        headers=headers,
        json={"installment_months": 2},
    )
    assert plan_response.status_code == 200, plan_response.text

    refunded_id = _create_invoice(client, headers)
    overpayment_response = client.post(
        f"/api/v1/invoices/{refunded_id}/payments",
        headers=headers,
        json={"amount_xof": "11000", "method": "CASH"},
    )
    assert overpayment_response.status_code == 200, overpayment_response.text
    refund_reference = f"REMBOURSEMENT-SYNTHETIQUE-{uuid.uuid4().hex}"
    refund_response = client.post(
        f"/api/v1/invoices/{refunded_id}/refund",
        headers=headers,
        json={"amount_xof": "1000", "reference": refund_reference},
    )
    assert refund_response.status_code == 200, refund_response.text

    with SessionLocal() as db:
        cancel_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "invoice.cancel",
                AuditEvent.entity_id == str(cancelled_id),
            )
            .one()
        )
        plan_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "invoice.payment_plan.create",
                AuditEvent.entity_id == str(planned_id),
            )
            .one()
        )
        refund_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "invoice.refund",
                AuditEvent.entity_id == str(refunded_id),
            )
            .one()
        )
        assert json.loads(cancel_event.payload or "{}") == {"old_status": "issued"}
        assert json.loads(plan_event.payload or "{}") == {
            "schedule_id": plan_response.json()["id"],
            "installment_months": 2,
        }
        assert json.loads(refund_event.payload or "{}") == {"amount_xof": "1000"}
        assert refund_reference not in (refund_event.payload or "")


def test_bnpl_payment_and_invoice_sync_roll_back_together(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    invoice_id = _create_invoice(client, headers)
    schedule_response = client.post(
        f"/api/v1/invoices/{invoice_id}/payment-plan",
        headers=headers,
        json={"installment_months": 2},
    )
    assert schedule_response.status_code == 200, schedule_response.text
    schedule_id = int(schedule_response.json()["id"])
    monkeypatch.setattr(
        bnpl_endpoint,
        "apply_bnpl_installment_to_invoice",
        _fail_invoice_sync,
    )

    with pytest.raises(RuntimeError, match="synthetic invoice synchronization failure"):
        client.post(
            f"/api/v1/billing/bnpl/schedule/{schedule_id}/pay",
            headers=headers,
            json={
                "schedule_id": schedule_id,
                "installment_number": 1,
                "amount_xof": 5000,
            },
        )

    with SessionLocal() as db:
        installment = (
            db.query(BNPLPayment)
            .filter(
                BNPLPayment.schedule_id == schedule_id,
                BNPLPayment.installment_number == 1,
            )
            .one()
        )
        invoice = db.get(Invoice, invoice_id)
        assert installment.status == "PENDING"
        assert installment.paid_at is None
        assert invoice is not None
        assert int(invoice.paid_xof) == 0
        assert db.query(InvoicePayment).filter(InvoicePayment.invoice_id == invoice_id).count() == 0
        assert (
            db.query(AuditEvent).filter(AuditEvent.event_type == "bnpl.payment.record").count() == 0
        )
