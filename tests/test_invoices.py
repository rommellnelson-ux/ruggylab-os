"""Tests — Comptabilité : facturation des examens, CMU, encaissements, créances."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _accountant(client, admin) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": f"compta_{u}", "password": "ComptaPass123!", "role": "accountant"},
    )
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"compta_{u}", "password": "ComptaPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _technician(client, admin) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"},
    )
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"tech_{u}", "password": "TechPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _new_invoice(client, hdrs, **over) -> dict:
    body = {
        "patient_label": "Patient Test",
        "patient_type": "UNINSURED",
        "lines": [
            {"exam_code": "NFS", "label": "Numération", "quantity": 1, "unit_price_xof": "5000"},
            {"exam_code": "GE", "label": "Goutte épaisse", "quantity": 2, "unit_price_xof": "2500"},
        ],
    }
    body.update(over)
    return client.post("/api/v1/invoices", headers=hdrs, json=body)


class TestInvoiceCmuMath:
    def test_uninsured_full_charge(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        r = _new_invoice(client, compta)
        assert r.status_code == 201, r.text
        inv = r.json()
        # 5000 + 2*2500 = 10000, non assuré → tout à la charge du patient
        assert float(inv["gross_total_xof"]) == 10000
        assert float(inv["net_total_xof"]) == 10000
        assert float(inv["cnam_part_xof"]) == 0
        assert float(inv["patient_due_xof"]) == 10000
        assert inv["status"] == "issued"
        assert inv["invoice_number"].startswith("FACT-")

    def test_insured_cnam_split(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        r = _new_invoice(client, compta, patient_type="INSURED", insurance_id="CNAM-CI-2026-001")
        inv = r.json()
        # assuré : CNAM 70 % = 7000, ticket modérateur 30 % = 3000
        assert float(inv["cnam_part_xof"]) == 7000
        assert float(inv["patient_due_xof"]) == 3000

    def test_discount_applied(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        inv = _new_invoice(client, compta, discount_xof="2000").json()
        assert float(inv["net_total_xof"]) == 8000
        assert float(inv["patient_due_xof"]) == 8000

    def test_insured_requires_insurance_id(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        assert _new_invoice(client, compta, patient_type="INSURED").status_code == 422


class TestPayments:
    def test_partial_then_full_payment(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        iid = _new_invoice(client, compta).json()["id"]

        inv = client.post(
            f"/api/v1/invoices/{iid}/payments",
            headers=compta,
            json={"amount_xof": "4000", "method": "MOBILE_MONEY"},
        ).json()
        assert inv["status"] == "partially_paid"
        assert float(inv["paid_xof"]) == 4000
        assert float(inv["balance_xof"]) == 6000

        inv = client.post(
            f"/api/v1/invoices/{iid}/payments",
            headers=compta,
            json={"amount_xof": "6000", "method": "CASH"},
        ).json()
        assert inv["status"] == "paid"
        assert float(inv["balance_xof"]) == 0

    def test_cancel_unpaid(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        iid = _new_invoice(client, compta).json()["id"]
        r = client.post(f"/api/v1/invoices/{iid}/cancel", headers=compta)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_cannot_cancel_paid(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        iid = _new_invoice(client, compta).json()["id"]
        client.post(
            f"/api/v1/invoices/{iid}/payments", headers=compta, json={"amount_xof": "10000"}
        )
        assert client.post(f"/api/v1/invoices/{iid}/cancel", headers=compta).status_code == 409


class TestFinanceSummary:
    def test_summary_aggregates(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        iid = _new_invoice(client, compta).json()["id"]
        client.post(f"/api/v1/invoices/{iid}/payments", headers=compta, json={"amount_xof": "4000"})
        s = client.get("/api/v1/invoices/summary", headers=compta).json()
        assert s["invoice_count"] >= 1
        assert float(s["collected_xof"]) >= 4000
        assert float(s["outstanding_xof"]) >= 6000


class TestInvoiceRbac:
    def test_technician_denied(self, client):
        admin = _auth(client)
        tech = _technician(client, admin)
        assert client.get("/api/v1/invoices", headers=tech).status_code == 403
        assert _new_invoice(client, tech).status_code == 403

    def test_admin_allowed(self, client):
        admin = _auth(client)
        assert client.get("/api/v1/invoices", headers=admin).status_code == 200

    def test_requires_auth(self, client):
        assert client.get("/api/v1/invoices").status_code == 401
