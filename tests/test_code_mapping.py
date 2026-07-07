"""Tests — Unification des vocabulaires biologiques (mapping + interprétation bioref)."""

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


def _seed_all(client, hdrs) -> None:
    """Charge le référentiel bioref + les correspondances."""
    client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
    client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)


def _make_result(client, hdrs, *, exam_code=None, data=None, sex="M") -> dict:
    pid = client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"CM-{_uid()}",
            "first_name": "Map",
            "last_name": "Test",
            "birth_date": "1980-01-01",
            "sex": sex,
        },
    ).json()["id"]
    sid = client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"CM-{_uid()}", "patient_id": pid, "status": "Recu"},
    ).json()["id"]
    body = {"sample_id": sid, "data_points": data or {"WBC": 5.0}, "is_critical": False}
    if exam_code:
        body["exam_code"] = exam_code
    r = client.post("/api/v1/results", headers=hdrs, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── Seed + CRUD ─────────────────────────────────────────────────────────────


class TestMappingSeedCrud:
    def test_seed_idempotent(self, client):
        hdrs = _auth(client)
        n = client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs).json()["created"]
        assert n >= 30
        assert (
            client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs).json()["created"] == 0
        )

    def test_list_contains_panels_and_components(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)
        rows = client.get("/api/v1/code-mappings", headers=hdrs).json()
        nfs = next(m for m in rows if m["canonical_code"] == "NFS")
        assert nfs["is_panel"] is True
        comps = [m for m in rows if m["component_of"] == "NFS"]
        assert {c["canonical_code"] for c in comps} >= {"HB", "WBC", "PLT", "NA"} - {"NA"}

    def test_create_and_deactivate(self, client):
        hdrs = _auth(client)
        r = client.post(
            "/api/v1/code-mappings",
            headers=hdrs,
            json={"canonical_code": f"X{_uid()[:4]}", "exam_code": "XX", "test_code": "CRP"},
        )
        assert r.status_code == 201
        mid = r.json()["id"]
        assert client.delete(f"/api/v1/code-mappings/{mid}", headers=hdrs).status_code == 200

    def test_create_requires_officer(self, client):
        hdrs = _auth(client)
        u = _uid()
        client.post(
            "/api/v1/users",
            headers=hdrs,
            json={"username": f"t_{u}", "password": "TechPass123!", "role": "technician"},
        )
        tok = (
            client.post(
                "/api/v1/login/access-token",
                data={"username": f"t_{u}", "password": "TechPass123!"},
            )
            .json()
            .get("access_token")
        )
        if tok:
            r = client.post(
                "/api/v1/code-mappings",
                headers={"Authorization": f"Bearer {tok}"},
                json={"canonical_code": "Z", "test_code": "CRP"},
            )
            assert r.status_code == 403


# ── Résolution (test endpoint) ──────────────────────────────────────────────


class TestMappingResolution:
    def test_glyc_to_glu_fast(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)
        r = client.post("/api/v1/code-mappings/test", headers=hdrs, json={"exam_code": "GLYC"})
        assert r.json()["bioref_test_code"] == "GLU_FAST"
        assert r.json()["canonical_code"] == "GLYC"

    def test_ge_to_mal_ge(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)
        assert (
            client.post(
                "/api/v1/code-mappings/test", headers=hdrs, json={"exam_code": "GE"}
            ).json()["bioref_test_code"]
            == "MAL_GE"
        )

    def test_aghbs_to_hbsag(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)
        assert (
            client.post(
                "/api/v1/code-mappings/test", headers=hdrs, json={"exam_code": "AGHBS"}
            ).json()["bioref_test_code"]
            == "HBSAG"
        )

    def test_nfs_panel_component(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)
        r = client.post(
            "/api/v1/code-mappings/test",
            headers=hdrs,
            json={"exam_code": "NFS", "analyte_code": "HGB"},
        )
        assert r.json()["is_panel"] is True
        assert r.json()["bioref_test_code"] == "HB"  # composant Hb

    def test_no_mapping(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)
        r = client.post(
            "/api/v1/code-mappings/test", headers=hdrs, json={"exam_code": "ZZZUNKNOWN"}
        )
        assert r.json()["matched"] is False
        assert r.json()["bioref_test_code"] is None

    def test_orphans_endpoint(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/code-mappings/seed-defaults", headers=hdrs)
        o = client.get("/api/v1/code-mappings/orphans", headers=hdrs).json()
        assert "exam_codes_unmapped" in o and "test_codes_unmapped" in o
        # GLYC est mappé → absent des orphelins
        assert "GLYC" not in o["exam_codes_unmapped"]
        assert o["exam_codes_unmapped"] == []
        assert o["test_codes_unmapped"] == []


# ── Branchement sur le cycle de vie du résultat ─────────────────────────────


class TestResultBiorefInterpretation:
    def test_ge_rejects_unrelated_analyte(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        patient_id = client.post(
            "/api/v1/patients",
            headers=hdrs,
            json={
                "ipp_unique_id": f"CM-{_uid()}",
                "first_name": "Map",
                "last_name": "Mismatch",
                "birth_date": "1980-01-01",
                "sex": "M",
            },
        ).json()["id"]
        sample_id = client.post(
            "/api/v1/samples",
            headers=hdrs,
            json={"barcode": f"CM-{_uid()}", "patient_id": patient_id, "status": "Recu"},
        ).json()["id"]
        response = client.post(
            "/api/v1/results",
            headers=hdrs,
            json={"sample_id": sample_id, "exam_code": "GE", "data_points": {"WBC": 5.0}},
        )
        assert response.status_code == 422
        assert "incompatible" in response.json()["detail"]

    def test_ge_positive_qualitative(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        # Goutte épaisse positive → statut anormal (normal = Négatif)
        r = _make_result(client, hdrs, exam_code="GE", data={"MAL_GE": "positive"})
        assert r["bioref_status"] == "POSITIF (anormal)"
        assert "paludisme" in (r["bioref_comment"] or "").lower()

    def test_ge_negative_qualitative(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        r = _make_result(client, hdrs, exam_code="GE", data={"MAL_GE": "négative"})
        assert r["bioref_status"] == "NÉGATIF"

    def test_glyc_numeric_critique(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        r = _make_result(client, hdrs, exam_code="GLYC", data={"GLYC": 0.30})
        assert r["bioref_status"] == "CRITIQUE BAS"
        assert "13" not in (r["bioref_reference_range"] or "")  # plage glycémie, pas HB

    def test_no_mapping_keeps_existing_behavior(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        # exam_code sans correspondance → pas d'interprétation bioref, flags inchangés
        r = _make_result(client, hdrs, exam_code="RAPIDX", data={"WBC": 5.0})
        assert r["bioref_status"] is None
        assert r["is_validated"] is True

    def test_no_exam_code_no_bioref(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        r = _make_result(client, hdrs, exam_code=None, data={"WBC": 5.0})
        assert r["bioref_status"] is None

    def test_nfs_panel_per_component(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        # Homme : HB 10 (<13 → BAS), WBC 5 (NORMAL), PLT 250 (NORMAL)
        r = _make_result(
            client, hdrs, exam_code="NFS", data={"HGB": 10, "WBC": 5, "PLT": 250}, sex="M"
        )
        # Panel → colonnes plates nulles (détail via endpoint)
        assert r["bioref_status"] is None
        detail = client.get(f"/api/v1/results/{r['id']}/bioref", headers=hdrs).json()
        assert detail["mapped"] is True
        assert detail["is_panel"] is True
        comps = {c["canonical_code"]: c for c in detail["components"]}
        assert comps["HB"]["bioref_status"] == "BAS"
        assert comps["WBC"]["bioref_status"] == "NORMAL"
        assert comps["PLT"]["bioref_status"] == "NORMAL"

    def test_panel_sex_variant_rbc(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        # RBC → pont sexe vers RBC_H (homme 4.5-5.9) ; 4.0 < 4.5 → BAS
        r = _make_result(client, hdrs, exam_code="NFS", data={"RBC": 4.0}, sex="M")
        detail = client.get(f"/api/v1/results/{r['id']}/bioref", headers=hdrs).json()
        comps = {c["canonical_code"]: c for c in detail["components"]}
        assert "RBC" in comps
        assert comps["RBC"]["bioref_status"] == "BAS"

    def test_single_test_endpoint_shape(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        r = _make_result(client, hdrs, exam_code="GLYC", data={"GLYC": 0.90})
        detail = client.get(f"/api/v1/results/{r['id']}/bioref", headers=hdrs).json()
        assert detail["mapped"] is True
        assert detail["is_panel"] is False
        assert detail["primary"]["bioref_status"] == "NORMAL"

    def test_result_without_mapping_endpoint(self, client):
        hdrs = _auth(client)
        _seed_all(client, hdrs)
        r = _make_result(client, hdrs, exam_code="ZZZ", data={"WBC": 5})
        detail = client.get(f"/api/v1/results/{r['id']}/bioref", headers=hdrs).json()
        assert detail["mapped"] is False
