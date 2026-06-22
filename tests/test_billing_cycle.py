"""Tests — bouclage du cycle facturation : tarifs, facture depuis prescription,
reçu PDF, plan de paiement BNPL optionnel.
"""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, admin, role: str) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": f"{role}_{u}", "password": "RolePass123!", "role": role},
    )
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"{role}_{u}", "password": "RolePass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _order_with_exams(client, admin, exams=("NFS", "GE")) -> int:
    pid = client.post(
        "/api/v1/patients",
        headers=admin,
        json={
            "ipp_unique_id": f"BC-{uuid.uuid4().hex[:8]}",
            "first_name": "Fac",
            "last_name": "Ture",
            "birth_date": "1980-01-01",
            "sex": "M",
        },
    ).json()["id"]
    r = client.post(
        "/api/v1/exam-orders",
        headers=admin,
        json={
            "patient_id": pid,
            "prescriber": "Dr Test",
            "exams": [{"exam_code": e} for e in exams],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestTariffs:
    def test_seed_is_idempotent_and_priced(self, client):
        admin = _auth(client)
        first = client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        assert first.status_code == 200
        assert first.json()["created"] > 0
        assert client.post("/api/v1/tariffs/seed-defaults", headers=admin).json()["created"] == 0
        rows = client.get("/api/v1/tariffs", headers=admin).json()
        nfs = next(t for t in rows if t["exam_code"] == "NFS")
        assert float(nfs["price_xof"]) == 5000  # Hématologie par défaut

    def test_upsert_requires_finance(self, client):
        admin = _auth(client)
        tech = _make_user(client, admin, "technician")
        r = client.put(
            "/api/v1/tariffs/NFS",
            headers=tech,
            json={"exam_code": "NFS", "label": "NFS", "price_xof": "9999", "is_active": True},
        )
        assert r.status_code == 403

    def test_upsert_updates_price(self, client):
        admin = _auth(client)
        r = client.put(
            "/api/v1/tariffs/CRP",
            headers=admin,
            json={"exam_code": "CRP", "label": "CRP", "price_xof": "4200", "is_active": True},
        )
        assert r.status_code == 200
        assert float(r.json()["price_xof"]) == 4200


class TestInvoiceFromOrder:
    def test_uninsured_totals_from_tariffs(self, client):
        admin = _auth(client)
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin, ("NFS", "GE"))
        r = client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=admin)
        assert r.status_code == 201, r.text
        inv = r.json()
        assert len(inv["lines"]) == 2
        assert float(inv["net_total_xof"]) == 7500  # 5000 (NFS) + 2500 (GE)
        assert float(inv["patient_due_xof"]) == 7500  # non assuré
        assert inv["exam_order_id"] == order_id

    def test_insured_applies_cnam_split(self, client):
        admin = _auth(client)
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin, ("NFS", "GE"))
        r = client.post(
            f"/api/v1/exam-orders/{order_id}/invoice",
            headers=admin,
            json={"patient_type": "INSURED", "insurance_id": "CNAM-CI-2026-1"},
        )
        assert r.status_code == 201, r.text
        inv = r.json()
        assert float(inv["cnam_part_xof"]) == 5250  # 70 %
        assert float(inv["patient_due_xof"]) == 2250  # 30 %

    def test_duplicate_invoice_rejected(self, client):
        admin = _auth(client)
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin)
        assert (
            client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=admin).status_code == 201
        )
        assert (
            client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=admin).status_code == 409
        )

    def test_accountant_cannot_generate_from_order(self, client):
        admin = _auth(client)
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin)
        compta = _make_user(client, admin, "accountant")
        # Le comptable est cloisonné du clinique (exam-orders) : 403.
        assert (
            client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=compta).status_code
            == 403
        )


class TestReceiptAndPaymentPlan:
    def _invoice(self, client, admin) -> dict:
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin, ("NFS", "GE"))
        return client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=admin).json()

    def test_receipt_pdf(self, client):
        admin = _auth(client)
        inv = self._invoice(client, admin)
        r = client.get(f"/api/v1/invoices/{inv['id']}/receipt.pdf", headers=admin)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"

    def test_payment_plan_optional_on_balance(self, client):
        admin = _auth(client)
        inv = self._invoice(client, admin)
        r = client.post(
            f"/api/v1/invoices/{inv['id']}/payment-plan",
            headers=admin,
            json={"installment_months": 3},
        )
        assert r.status_code == 200, r.text
        plan = r.json()
        assert plan["installment_months"] == 3
        # La facture porte désormais la référence du plan.
        inv2 = client.get(f"/api/v1/invoices/{inv['id']}", headers=admin).json()
        assert inv2["payment_plan_id"] == plan["id"]

    def test_payment_plan_rejected_twice(self, client):
        admin = _auth(client)
        inv = self._invoice(client, admin)
        client.post(
            f"/api/v1/invoices/{inv['id']}/payment-plan",
            headers=admin,
            json={"installment_months": 2},
        )
        again = client.post(
            f"/api/v1/invoices/{inv['id']}/payment-plan",
            headers=admin,
            json={"installment_months": 2},
        )
        assert again.status_code == 409

    def test_payment_plan_rejected_when_paid(self, client):
        admin = _auth(client)
        inv = self._invoice(client, admin)
        # Solde le reste à charge intégral.
        client.post(
            f"/api/v1/invoices/{inv['id']}/payments",
            headers=admin,
            json={"amount_xof": inv["patient_due_xof"]},
        )
        r = client.post(
            f"/api/v1/invoices/{inv['id']}/payment-plan",
            headers=admin,
            json={"installment_months": 3},
        )
        assert r.status_code == 409

    def test_receipt_requires_finance(self, client):
        admin = _auth(client)
        inv = self._invoice(client, admin)
        tech = _make_user(client, admin, "technician")
        assert (
            client.get(f"/api/v1/invoices/{inv['id']}/receipt.pdf", headers=tech).status_code == 403
        )


class TestBnplInvoiceSync:
    def _invoice(self, client, admin) -> dict:
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin, ("NFS", "GE"))  # reste patient 7500
        return client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=admin).json()

    def test_bnpl_installment_reflects_on_invoice(self, client):
        admin = _auth(client)
        inv = self._invoice(client, admin)
        plan = client.post(
            f"/api/v1/invoices/{inv['id']}/payment-plan",
            headers=admin,
            json={"installment_months": 3},
        ).json()
        sid = plan["id"]

        # Échéance 1 réglée via BNPL → répercutée sur la facture.
        r = client.post(
            f"/api/v1/billing/bnpl/schedule/{sid}/pay",
            headers=admin,
            json={"schedule_id": sid, "installment_number": 1, "amount_xof": 2500},
        )
        assert r.status_code in (200, 201), r.text
        inv1 = client.get(f"/api/v1/invoices/{inv['id']}", headers=admin).json()
        assert float(inv1["paid_xof"]) == 2500
        assert inv1["status"] == "partially_paid"
        assert float(inv1["balance_xof"]) == 5000

        # Solde des deux échéances restantes → facture payée.
        client.post(
            f"/api/v1/billing/bnpl/schedule/{sid}/pay",
            headers=admin,
            json={"schedule_id": sid, "installment_number": 2, "amount_xof": 2500},
        )
        client.post(
            f"/api/v1/billing/bnpl/schedule/{sid}/pay",
            headers=admin,
            json={"schedule_id": sid, "installment_number": 3, "amount_xof": 2500},
        )
        inv2 = client.get(f"/api/v1/invoices/{inv['id']}", headers=admin).json()
        assert float(inv2["paid_xof"]) == 7500
        assert inv2["status"] == "paid"

    def test_standalone_bnpl_plan_touches_no_invoice(self, client):
        admin = _auth(client)
        # Plan BNPL autonome (sans facture liée) : ne doit rien casser.
        plan = client.post(
            "/api/v1/billing/bnpl/schedule",
            headers=admin,
            json={"patient_ref": "AUTONOME", "total_amount_xof": 6000, "installment_months": 2},
        ).json()
        r = client.post(
            f"/api/v1/billing/bnpl/schedule/{plan['id']}/pay",
            headers=admin,
            json={"schedule_id": plan["id"], "installment_number": 1, "amount_xof": 3000},
        )
        assert r.status_code in (200, 201)


class TestBnplRequiresFinance:
    """Séparation des tâches : BNPL est une opération financière (comptable/admin)."""

    def test_technician_denied_bnpl_create(self, client):
        admin = _auth(client)
        tech = _make_user(client, admin, "technician")
        r = client.post(
            "/api/v1/billing/bnpl/schedule",
            headers=tech,
            json={"patient_ref": "X", "total_amount_xof": 5000, "installment_months": 2},
        )
        assert r.status_code == 403

    def test_officer_denied_bnpl_overdue(self, client):
        admin = _auth(client)
        officer = _make_user(client, admin, "officer")
        assert client.get("/api/v1/billing/bnpl/overdue", headers=officer).status_code == 403


class TestAgingReport:
    def test_aging_buckets_capture_outstanding(self, client):
        admin = _auth(client)
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin, ("NFS", "GE"))
        client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=admin)

        r = client.get("/api/v1/invoices/aging", headers=admin)
        assert r.status_code == 200, r.text
        report = r.json()
        assert len(report["buckets"]) == 4
        assert float(report["total_outstanding_xof"]) >= 7500
        # Facture émise à l'instant → tranche 0-30 jours.
        recent = next(b for b in report["buckets"] if b["label"] == "0-30 j")
        assert float(recent["outstanding_xof"]) >= 7500

    def test_aging_requires_finance(self, client):
        admin = _auth(client)
        tech = _make_user(client, admin, "technician")
        assert client.get("/api/v1/invoices/aging", headers=tech).status_code == 403


class TestOverpaymentAccepted:
    def test_overpayment_becomes_credit(self, client):
        admin = _auth(client)
        client.post("/api/v1/tariffs/seed-defaults", headers=admin)
        order_id = _order_with_exams(client, admin, ("NFS", "GE"))  # reste 7500
        inv = client.post(f"/api/v1/exam-orders/{order_id}/invoice", headers=admin).json()

        # Encaissement supérieur au reste à charge : accepté comme avoir.
        r = client.post(
            f"/api/v1/invoices/{inv['id']}/payments",
            headers=admin,
            json={"amount_xof": "8000"},
        )
        assert r.status_code == 200, r.text
        paid = r.json()
        assert paid["status"] == "paid"
        assert float(paid["balance_xof"]) == 0
        assert float(paid["credit_xof"]) == 500  # 8000 - 7500

        # Le trop-perçu remonte dans la synthèse comptable.
        summary = client.get("/api/v1/invoices/summary", headers=admin).json()
        assert float(summary["credit_xof"]) >= 500
