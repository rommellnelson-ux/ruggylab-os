"""Tests de la route de saisie des résultats qualitatifs (Flux 3)."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _sample(client, admin) -> str:
    pid = client.post(
        "/api/v1/patients",
        headers=admin,
        json={
            "ipp_unique_id": f"QL-{uuid.uuid4().hex[:8]}",
            "first_name": "Qual",
            "last_name": "Test",
            "birth_date": "1985-05-05",
            "sex": "F",
        },
    ).json()["id"]
    barcode = f"QL-{uuid.uuid4().hex[:10]}"
    client.post(
        "/api/v1/samples",
        headers=admin,
        json={"barcode": barcode, "patient_id": pid, "status": "Recu"},
    )
    return barcode


def test_positive_parasitology_is_critical(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    r = client.post(
        "/api/v1/results/qualitative",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "category": "parasitology",
            "findings": {
                "is_negative": False,
                "observations": [{"organism": "Plasmodium falciparum", "density": "+++"}],
                "comment": "Trophozoïtes nombreux.",
            },
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_critical"] is True
    assert body["result_id"] > 0


def test_negative_result_not_critical(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    r = client.post(
        "/api/v1/results/qualitative",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "category": "parasitology",
            "findings": {"is_negative": True, "observations": [], "comment": None},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["is_critical"] is False


def test_negative_with_observations_is_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    r = client.post(
        "/api/v1/results/qualitative",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "category": "cytology",
            "findings": {
                "is_negative": True,
                "observations": [{"organism": "Levures (Candida albicans)", "density": "Rares"}],
            },
        },
    )
    assert r.status_code == 422


def test_positive_without_observation_is_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    r = client.post(
        "/api/v1/results/qualitative",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "category": "cytology",
            "findings": {"is_negative": False, "observations": []},
        },
    )
    assert r.status_code == 422


def test_invalid_density_is_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    r = client.post(
        "/api/v1/results/qualitative",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "category": "parasitology",
            "findings": {
                "is_negative": False,
                "observations": [{"organism": "Schistosoma haematobium", "density": "beaucoup"}],
            },
        },
    )
    assert r.status_code == 422


def test_unknown_barcode_returns_404(client) -> None:
    admin = _auth(client)
    r = client.post(
        "/api/v1/results/qualitative",
        headers=admin,
        json={
            "sample_barcode": "DOES-NOT-EXIST",
            "category": "smear",
            "findings": {
                "is_negative": False,
                "observations": [{"organism": "Gamétocytes", "density": "+"}],
            },
        },
    )
    assert r.status_code == 404


def test_image_url_is_persisted(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    reserved = client.post(
        "/api/v1/imaging/capture-microscope",
        headers=admin,
        json={"sample_barcode": barcode},
    ).json()["image_url"]
    r = client.post(
        "/api/v1/results/qualitative",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "category": "smear",
            "image_url": reserved,
            "findings": {
                "is_negative": False,
                "observations": [{"organism": "Schizontes", "density": "++"}],
            },
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["image_url"] == reserved


def test_microscopy_template_served(client) -> None:
    resp = client.get("/app/microscopy")
    assert resp.status_code == 200
    assert "Cockpit Microscopie" in resp.text
    assert "/results/qualitative" in resp.text
    assert "capture-microscope" in resp.text
