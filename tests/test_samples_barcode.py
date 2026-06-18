"""Tests — résolution d'un échantillon par code-barres (saisie labo réel)."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_resolve_sample_by_barcode(client):
    hdrs = _auth(client)
    pid = client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"BC-{uuid.uuid4().hex[:8]}",
            "first_name": "Bar",
            "last_name": "Code",
            "birth_date": "1980-01-01",
            "sex": "M",
        },
    ).json()["id"]
    barcode = f"SCAN-{uuid.uuid4().hex[:10]}"
    sid = client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": barcode, "patient_id": pid, "status": "Recu"},
    ).json()["id"]

    r = client.get(f"/api/v1/samples/by-barcode/{barcode}", headers=hdrs)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == sid
    assert r.json()["barcode"] == barcode


def test_unknown_barcode_404(client):
    hdrs = _auth(client)
    assert client.get("/api/v1/samples/by-barcode/INCONNU-XYZ", headers=hdrs).status_code == 404


def test_by_barcode_requires_auth(client):
    assert client.get("/api/v1/samples/by-barcode/whatever").status_code == 401
