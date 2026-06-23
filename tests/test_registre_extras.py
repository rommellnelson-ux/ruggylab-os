"""Tests — compléments registre : n° labo, champs patient/prescription/échantillon,
notifications épidémiologiques (MADO), lots de réactifs (FEFO).
"""

from __future__ import annotations

import re
import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user(client, admin, role: str) -> dict[str, str]:
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


def _patient(client, admin, **extra) -> dict:
    body = {
        "ipp_unique_id": f"RX-{uuid.uuid4().hex[:8]}",
        "first_name": "Re",
        "last_name": "Gistre",
        "birth_date": "1980-01-01",
        "sex": "F",
        **extra,
    }
    return client.post("/api/v1/patients", headers=admin, json=body).json()


class TestPatientAndOrderFields:
    def test_patient_phone_and_quarter(self, client):
        admin = _auth(client)
        p = _patient(client, admin, phone="+225 0700000000", residence_quarter="Yopougon")
        assert p["phone"] == "+225 0700000000"
        assert p["residence_quarter"] == "Yopougon"

    def test_order_requesting_service(self, client):
        admin = _auth(client)
        pid = _patient(client, admin)["id"]
        r = client.post(
            "/api/v1/exam-orders",
            headers=admin,
            json={
                "patient_id": pid,
                "requesting_service": "Urgences",
                "exams": [{"exam_code": "NFS"}],
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["requesting_service"] == "Urgences"


class TestLabNumber:
    def test_sample_gets_lab_number(self, client):
        admin = _auth(client)
        pid = _patient(client, admin)["id"]
        r = client.post(
            "/api/v1/samples",
            headers=admin,
            json={
                "barcode": f"LN-{uuid.uuid4().hex[:8]}",
                "patient_id": pid,
                "collected_by_label": "Inf. Diallo",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert re.match(r"^\d{4}-\d{6}$", body["lab_number"])
        assert body["collected_by_label"] == "Inf. Diallo"


class TestEpiNotifications:
    def test_declare_list_transmit(self, client):
        admin = _auth(client)
        d = client.post(
            "/api/v1/epi-notifications",
            headers=admin,
            json={"pathology": "Paludisme grave", "residence_quarter": "Abobo"},
        )
        assert d.status_code == 201, d.text
        nid = d.json()["id"]
        assert d.json()["status"] == "to_send"

        officer = _user(client, admin, "officer")
        t = client.post(
            f"/api/v1/epi-notifications/{nid}/transmit",
            headers=officer,
            json={"channel": "Téléphone district"},
        )
        assert t.status_code == 200, t.text
        assert t.json()["status"] == "sent_to_district"
        assert t.json()["notified_at"] is not None

    def test_transmit_requires_officer(self, client):
        admin = _auth(client)
        nid = client.post(
            "/api/v1/epi-notifications", headers=admin, json={"pathology": "Cholera"}
        ).json()["id"]
        tech = _user(client, admin, "technician")
        assert (
            client.post(f"/api/v1/epi-notifications/{nid}/transmit", headers=tech, json={}).status_code
            == 403
        )


class TestReagentLotsFefo:
    def _reagent(self, client, admin) -> int:
        return client.post(
            "/api/v1/reagents",
            headers=admin,
            json={"name": f"Reactif-{uuid.uuid4().hex[:6]}", "unit": "test"},
        ).json()["id"]

    def test_fefo_consumes_soonest_expiry_first(self, client):
        admin = _auth(client)
        rid = self._reagent(client, admin)
        # Lot A périme plus tard, Lot B plus tôt → B doit être consommé en premier.
        lot_a = client.post(
            "/api/v1/reagent-lots",
            headers=admin,
            json={"reagent_id": rid, "lot_number": "A", "expiry_date": "2027-12-31", "quantity": 10},
        ).json()
        lot_b = client.post(
            "/api/v1/reagent-lots",
            headers=admin,
            json={"reagent_id": rid, "lot_number": "B", "expiry_date": "2026-09-30", "quantity": 5},
        ).json()
        client.post(
            "/api/v1/reagent-lots/consume", headers=admin, json={"reagent_id": rid, "quantity": 6}
        )
        lots = {
            lot["lot_number"]: lot
            for lot in client.get(
                f"/api/v1/reagent-lots?reagent_id={rid}", headers=admin
            ).json()
        }
        assert lots["B"]["quantity"] == 0  # B (péremption proche) épuisé
        assert lots["B"]["status"] == "exhausted"
        assert lots["A"]["quantity"] == 9  # 1 pris sur A
        del lot_a, lot_b

    def test_insufficient_quantity_rejected(self, client):
        admin = _auth(client)
        rid = self._reagent(client, admin)
        client.post(
            "/api/v1/reagent-lots",
            headers=admin,
            json={"reagent_id": rid, "lot_number": "X", "quantity": 2},
        )
        r = client.post(
            "/api/v1/reagent-lots/consume", headers=admin, json={"reagent_id": rid, "quantity": 5}
        )
        assert r.status_code == 409
