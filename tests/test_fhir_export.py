"""Tests for the FHIR R4 DiagnosticReport export endpoint.

Covers:
- GET /api/v1/results/{id}/fhir  → 200 with valid FHIR JSON
- FHIR structure: resourceType, status, LOINC code, contained observations
- Patient demographics embedded as contained resource
- Unknown parameters are ignored gracefully
- 404 when result does not exist
- Interpretation flags from data_points status values
- overall_flags surfaced as conclusionCode
"""

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(client):
    resp = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_patient(client, headers) -> int:
    resp = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-FHIR-001",
            "first_name": "Marie",
            "last_name": "Dupont",
            "birth_date": "1985-03-15",
            "sex": "F",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_sample(client, headers, patient_id: int) -> int:
    resp = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": "FHIR-SAMPLE-001",
            "patient_id": patient_id,
            "status": "Recu",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_result(client, headers, sample_id: int, data_points: dict) -> int:
    resp = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "data_points": data_points,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# NFS data_points fixture — mirrors real DH36 validated output
NFS_DATA_POINTS = {
    "WBC": {"value": 7.2, "unit": "10^9/L", "status": "NORMAL"},
    "RBC": {"value": 4.8, "unit": "10^12/L", "status": "NORMAL"},
    "HGB": {"value": 14.5, "unit": "g/dL", "status": "NORMAL"},
    "HCT": {"value": 43.1, "unit": "%", "status": "NORMAL"},
    "MCV": {"value": 89.8, "unit": "fL", "status": "NORMAL"},
    "MCH": {"value": 30.2, "unit": "pg", "status": "NORMAL"},
    "MCHC": {"value": 33.6, "unit": "g/dL", "status": "NORMAL"},
    "PLT": {"value": 210, "unit": "10^9/L", "status": "NORMAL"},
}

NFS_WITH_ANOMALIES = {
    "WBC": {"value": 2.1, "unit": "10^9/L", "status": "CRITICAL_LOW"},
    "HGB": {"value": 6.8, "unit": "g/dL", "status": "LOW"},
    "PLT": {"value": 42, "unit": "10^9/L", "status": "CRITICAL_LOW"},
    "overall_flags": ["ANEMIE_SEVERE", "LEUCOPENIE", "THROMBOPENIE_SEVERE", "PANTOPENIQUE"],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fhir_export_returns_diagnostic_report(client):
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_DATA_POINTS)

    resp = client.get(f"/api/v1/results/{rid}/fhir", headers=headers)
    assert resp.status_code == 200, resp.text

    doc = resp.json()
    assert doc["resourceType"] == "DiagnosticReport"
    assert doc["id"] == f"ruggylab-result-{rid}"


def test_fhir_export_content_type(client):
    """The endpoint must respond with application/fhir+json."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_DATA_POINTS)

    resp = client.get(f"/api/v1/results/{rid}/fhir", headers=headers)
    assert "application/fhir+json" in resp.headers["content-type"]


def test_fhir_export_loinc_cbc_code(client):
    """The top-level code must use LOINC 58410-2 (CBC panel)."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_DATA_POINTS)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    codings = doc["code"]["coding"]
    assert any(c["code"] == "58410-2" and c["system"] == "http://loinc.org" for c in codings)


def test_fhir_export_contains_observations(client):
    """Each NFS parameter must appear as a contained Observation."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_DATA_POINTS)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    obs_resources = [r for r in doc["contained"] if r.get("resourceType") == "Observation"]

    # All 8 NFS parameters should be present
    assert len(obs_resources) == 8

    # Check WBC has correct LOINC code
    wbc_obs = next(o for o in obs_resources if o["id"] == "obs-wbc")
    assert wbc_obs["code"]["coding"][0]["code"] == "6690-2"
    assert wbc_obs["code"]["coding"][0]["system"] == "http://loinc.org"
    assert wbc_obs["valueQuantity"]["value"] == pytest.approx(7.2)


def test_fhir_export_preserves_ucum_source_unit(client):
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    payload = dict(NFS_DATA_POINTS)
    payload["HGB"] = {"value": 132, "unit": "g/L", "status": "NORMAL"}
    rid = _create_result(client, headers, sid, payload)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    hgb = next(item for item in doc["contained"] if item.get("id") == "obs-hgb")
    assert hgb["valueQuantity"]["value"] == 132
    assert hgb["valueQuantity"]["code"] == "g/L"


def test_fhir_export_contains_patient(client):
    """Patient demographics must be embedded as a contained Patient resource."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_DATA_POINTS)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    patients = [r for r in doc["contained"] if r.get("resourceType") == "Patient"]
    assert len(patients) == 1

    patient = patients[0]
    assert patient["name"][0]["family"] == "Dupont"
    assert "Marie" in patient["name"][0]["given"]
    assert patient["birthDate"] == "1985-03-15"
    assert patient["gender"] == "female"


def test_fhir_export_result_refs(client):
    """result[] must contain references to all contained Observations."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_DATA_POINTS)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    refs = {r["reference"] for r in doc["result"]}

    assert "#obs-wbc" in refs
    assert "#obs-hgb" in refs
    assert "#obs-plt" in refs


def test_fhir_export_normal_interpretation_code(client):
    """Normal parameters must carry the 'N' FHIR interpretation code."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_DATA_POINTS)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    obs_resources = [r for r in doc["contained"] if r.get("resourceType") == "Observation"]

    for obs in obs_resources:
        interp = obs.get("interpretation", [])
        if interp:
            code = interp[0]["coding"][0]["code"]
            assert code == "N", f"Expected N for {obs['id']}, got {code}"


def test_fhir_export_anomaly_interpretation_codes(client):
    """Critical-low parameters must carry 'LL'; low parameters 'L'."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_WITH_ANOMALIES)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    obs_map = {o["id"]: o for o in doc["contained"] if o.get("resourceType") == "Observation"}

    # WBC is CRITICAL_LOW → LL
    assert obs_map["obs-wbc"]["interpretation"][0]["coding"][0]["code"] == "LL"
    # HGB is LOW → L
    assert obs_map["obs-hgb"]["interpretation"][0]["coding"][0]["code"] == "L"


def test_fhir_export_overall_flags_as_conclusion_codes(client):
    """overall_flags must surface as conclusionCode entries."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)
    rid = _create_result(client, headers, sid, NFS_WITH_ANOMALIES)

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    flag_codes = {c["coding"][0]["code"] for c in doc.get("conclusionCode", [])}

    assert "PANTOPENIQUE" in flag_codes
    assert "ANEMIE_SEVERE" in flag_codes


def test_fhir_export_unknown_keys_ignored(client):
    """Non-NFS keys in data_points (e.g. malaria_ai) must not crash the export."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)

    mixed_data = {
        "WBC": {"value": 5.5, "unit": "10^9/L", "status": "NORMAL"},
        "malaria_ai": {"label": "negative", "confidence": 0.92},
        "overall_flags": [],
    }
    rid = _create_result(client, headers, sid, mixed_data)

    resp = client.get(f"/api/v1/results/{rid}/fhir", headers=headers)
    assert resp.status_code == 200
    doc = resp.json()
    obs_resources = [r for r in doc["contained"] if r.get("resourceType") == "Observation"]
    assert len(obs_resources) == 1  # only WBC


def test_fhir_export_404_for_unknown_result(client):
    headers = _auth(client)
    resp = client.get("/api/v1/results/999999/fhir", headers=headers)
    assert resp.status_code == 404


def test_fhir_export_is_final_while_biological_review_is_pending(client):
    """La revue interne différée ne rend pas le résultat patient provisoire."""
    headers = _auth(client)
    pid = _create_patient(client, headers)
    sid = _create_sample(client, headers, pid)

    resp = client.post(
        "/api/v1/results",
        headers=headers,
        json={"sample_id": sid, "data_points": NFS_DATA_POINTS},
    )
    assert resp.status_code == 201
    rid = resp.json()["id"]

    doc = client.get(f"/api/v1/results/{rid}/fhir", headers=headers).json()
    assert doc["status"] == "final"
