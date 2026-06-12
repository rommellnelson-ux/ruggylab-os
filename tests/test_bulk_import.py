"""Tests — Import en lot CSV (patients + réactifs)."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:8]


class TestBulkImportPatients:
    def test_import_valid_patients(self, client):
        hdrs = _auth(client)
        u = _uid()
        csv = (
            "ipp_unique_id,first_name,last_name,birth_date,sex,rank\n"
            f"BI-{u}-1,Awa,Kone,1990-05-12,F,Sergent\n"
            f"BI-{u}-2,Yao,Brou,1985-11-03,M,Caporal\n"
        )
        r = client.post("/api/v1/bulk-import/patients", headers=hdrs, json={"csv": csv})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 2
        assert data["created"] == 2
        assert data["errors"] == []

    def test_import_reports_invalid_rows(self, client):
        hdrs = _auth(client)
        u = _uid()
        csv = (
            "ipp_unique_id,first_name,last_name,birth_date,sex,rank\n"
            f"BI-{u}-ok,Valid,Patient,1990-05-12,F,Sergent\n"
            f"BI-{u}-bad,Bad,Date,not-a-date,M,Caporal\n"
            f"BI-{u}-future,Future,Birth,2099-01-01,F,\n"
        )
        r = client.post("/api/v1/bulk-import/patients", headers=hdrs, json={"csv": csv})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 3
        assert data["created"] == 1
        assert len(data["errors"]) == 2
        rows_with_errors = {e["row"] for e in data["errors"]}
        assert rows_with_errors == {3, 4}  # lignes CSV (en-tête = ligne 1)

    def test_import_detects_duplicate_in_file(self, client):
        hdrs = _auth(client)
        u = _uid()
        csv = (
            "ipp_unique_id,first_name,last_name,birth_date,sex\n"
            f"BI-{u}-dup,A,B,1990-01-01,M\n"
            f"BI-{u}-dup,C,D,1991-01-01,F\n"
        )
        r = client.post("/api/v1/bulk-import/patients", headers=hdrs, json={"csv": csv})
        data = r.json()
        assert data["created"] == 1
        assert len(data["errors"]) == 1

    def test_import_detects_existing_patient(self, client):
        hdrs = _auth(client)
        ipp = f"BI-EXIST-{_uid()}"
        client.post(
            "/api/v1/patients",
            headers=hdrs,
            json={
                "ipp_unique_id": ipp,
                "first_name": "X",
                "last_name": "Y",
                "birth_date": "1980-01-01",
                "sex": "M",
            },
        )
        csv = f"ipp_unique_id,first_name,last_name,birth_date,sex\n{ipp},A,B,1990-01-01,M\n"
        r = client.post("/api/v1/bulk-import/patients", headers=hdrs, json={"csv": csv})
        data = r.json()
        assert data["created"] == 0
        assert len(data["errors"]) == 1

    def test_import_requires_officer(self, client):
        hdrs = _auth(client)
        u = _uid()
        client.post(
            "/api/v1/users",
            headers=hdrs,
            json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"},
        )
        tok = (
            client.post(
                "/api/v1/login/access-token",
                data={"username": f"tech_{u}", "password": "TechPass123!"},
            )
            .json()
            .get("access_token")
        )
        if tok:
            r = client.post(
                "/api/v1/bulk-import/patients",
                headers={"Authorization": f"Bearer {tok}"},
                json={"csv": "ipp_unique_id,first_name,last_name,birth_date\nX,A,B,1990-01-01\n"},
            )
            assert r.status_code == 403


class TestBulkImportReagents:
    def test_import_valid_reagents(self, client):
        hdrs = _auth(client)
        u = _uid()
        csv = (
            "name,category,unit,current_stock,alert_threshold,lot_number,expiry_date,supplier\n"
            f"Diluant-{u},Hema,L,20,5,LOT-{u},2027-01-01,Sysmex\n"
            f"Lyse-{u},Hema,mL,500,100,LOT2-{u},2026-09-30,Sysmex\n"
        )
        r = client.post("/api/v1/bulk-import/reagents", headers=hdrs, json={"csv": csv})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 2
        assert data["created"] == 2
        assert data["errors"] == []

    def test_import_reagent_missing_name(self, client):
        hdrs = _auth(client)
        csv = "name,unit,current_stock\n,L,10\n"
        r = client.post("/api/v1/bulk-import/reagents", headers=hdrs, json={"csv": csv})
        data = r.json()
        assert data["created"] == 0
        assert len(data["errors"]) == 1

    def test_import_reagent_minimal_columns(self, client):
        hdrs = _auth(client)
        u = _uid()
        csv = f"name\nMinimal-{u}\n"
        r = client.post("/api/v1/bulk-import/reagents", headers=hdrs, json={"csv": csv})
        data = r.json()
        assert data["created"] == 1
        assert data["errors"] == []

    def test_empty_csv_rejected(self, client):
        hdrs = _auth(client)
        r = client.post("/api/v1/bulk-import/reagents", headers=hdrs, json={"csv": ""})
        assert r.status_code == 422  # min_length=1
