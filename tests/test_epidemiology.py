"""Tests du tableau de bord épidémiologique.

POST /api/v1/epidemiology/dashboard

Couvre :
1.  Structure de réponse — tous les champs requis présents
2.  Taux de critiques global calculé correctement
3.  ParameterStats — critical_rate par paramètre correct
4.  Filtre par date — résultats hors période absents
5.  Filtre par facility_ids (equipment_id)
6.  Tendance journalière cohérente avec le nombre total de critiques
7.  401 sans token
8.  Réponse vide mais valide si aucun résultat dans la période
9.  Filtre par paramètres (parameters=[])
10. Tri décroissant des parameter_stats par critical_rate
"""

from __future__ import annotations

import datetime

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DASHBOARD_URL = "/api/v1/epidemiology/dashboard"


def _auth(client) -> dict:
    resp = client.post(
        "/api/v1/login/access-token",
        data={
            "username": "admin",
            "password": "change_me_admin_password",  # pragma: allowlist secret
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_patient(client, headers, suffix: str = "001") -> int:
    resp = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"IPP-EPID-{suffix}",
            "first_name": "Test",
            "last_name": f"Patient-{suffix}",
            "birth_date": "1990-01-01",
            "sex": "M",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_sample(client, headers, patient_id: int, barcode: str = "EPID-BC-001") -> int:
    resp = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": barcode, "patient_id": patient_id, "status": "Recu"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_result(
    client,
    headers,
    sample_id: int,
    data_points: dict,
    equipment_id: int | None = None,
) -> int:
    payload: dict = {"sample_id": sample_id, "data_points": data_points}
    if equipment_id is not None:
        payload["equipment_id"] = equipment_id
    resp = client.post("/api/v1/results", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_equipment(client, headers, name: str = "Analyser-A") -> int:
    resp = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": name, "type": "hematology"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _dashboard(client, headers, body: dict | None = None) -> dict:
    resp = client.post(DASHBOARD_URL, headers=headers, json=body or {})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------

NORMAL_DATA = {
    "WBC": {"value": 7.2, "unit": "10^9/L", "status": "NORMAL"},
    "HGB": {"value": 14.5, "unit": "g/dL", "status": "NORMAL"},
    "PLT": {"value": 210, "unit": "10^9/L", "status": "NORMAL"},
}

CRITICAL_DATA = {
    "WBC": {"value": 1.5, "unit": "10^9/L", "status": "CRITICAL_LOW"},
    "HGB": {"value": 5.0, "unit": "g/dL", "status": "CRITICAL_LOW"},
    "PLT": {"value": 20, "unit": "10^9/L", "status": "CRITICAL_HIGH"},
}

MIXED_DATA = {
    "WBC": {"value": 2.1, "unit": "10^9/L", "status": "CRITICAL_LOW"},
    "HGB": {"value": 12.0, "unit": "g/dL", "status": "NORMAL"},
    "PLT": {"value": 150, "unit": "10^9/L", "status": "NORMAL"},
}


# ---------------------------------------------------------------------------
# Test 1 : Structure de la réponse
# ---------------------------------------------------------------------------


def test_dashboard_response_structure(client):
    """Tous les champs obligatoires doivent être présents dans la réponse."""
    headers = _auth(client)
    data = _dashboard(client, headers)

    required_top_keys = {
        "period_start",
        "period_end",
        "total_results",
        "total_critical",
        "overall_critical_rate",
        "parameter_stats",
        "facility_stats",
        "daily_critical_trend",
    }
    assert required_top_keys.issubset(data.keys()), (
        f"Clés manquantes : {required_top_keys - data.keys()}"
    )

    assert isinstance(data["parameter_stats"], list)
    assert isinstance(data["facility_stats"], list)
    assert isinstance(data["daily_critical_trend"], list)


# ---------------------------------------------------------------------------
# Test 2 : Calcul correct du taux critique global
# ---------------------------------------------------------------------------


def test_overall_critical_rate(client):
    """overall_critical_rate doit être total_critical / total_results."""
    headers = _auth(client)
    pid = _create_patient(client, headers, "CR-001")
    sid1 = _create_sample(client, headers, pid, "BC-CR-001")
    sid2 = _create_sample(client, headers, pid, "BC-CR-002")
    sid3 = _create_sample(client, headers, pid, "BC-CR-003")

    today = datetime.date.today().isoformat()
    _create_result(client, headers, sid1, CRITICAL_DATA)  # critique
    _create_result(client, headers, sid2, NORMAL_DATA)  # normal
    _create_result(client, headers, sid3, NORMAL_DATA)  # normal

    data = _dashboard(client, headers, {"start_date": today, "end_date": today})

    assert data["total_results"] >= 3
    assert data["total_critical"] >= 1
    expected_rate = data["total_critical"] / data["total_results"]
    assert abs(data["overall_critical_rate"] - expected_rate) < 1e-3


# ---------------------------------------------------------------------------
# Test 3 : Calcul des ParameterStats
# ---------------------------------------------------------------------------


def test_parameter_stats_critical_rate(client):
    """critical_rate de chaque paramètre = critical_count / total_results."""
    headers = _auth(client)
    pid = _create_patient(client, headers, "PS-001")
    sid1 = _create_sample(client, headers, pid, "BC-PS-001")
    sid2 = _create_sample(client, headers, pid, "BC-PS-002")

    today = datetime.date.today().isoformat()
    _create_result(client, headers, sid1, CRITICAL_DATA)
    _create_result(client, headers, sid2, NORMAL_DATA)

    data = _dashboard(client, headers, {"start_date": today, "end_date": today})

    for ps in data["parameter_stats"]:
        assert "parameter" in ps
        assert "total_results" in ps
        assert "critical_count" in ps
        assert "critical_rate" in ps
        if ps["total_results"] > 0:
            expected = ps["critical_count"] / ps["total_results"]
            assert abs(ps["critical_rate"] - expected) < 1e-3, (
                f"Mauvais taux pour {ps['parameter']}"
            )


# ---------------------------------------------------------------------------
# Test 4 : Filtre par date — résultats hors période absents
# ---------------------------------------------------------------------------


def test_date_filter_excludes_out_of_range(client):
    """Un résultat créé aujourd'hui ne doit pas apparaître si on filtre sur hier."""
    headers = _auth(client)
    pid = _create_patient(client, headers, "DF-001")
    sid = _create_sample(client, headers, pid, "BC-DF-001")
    _create_result(client, headers, sid, CRITICAL_DATA)

    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    data = _dashboard(client, headers, {"start_date": yesterday, "end_date": yesterday})

    # Le résultat d'aujourd'hui NE doit PAS être comptabilisé
    assert data["total_results"] == 0
    assert data["total_critical"] == 0


# ---------------------------------------------------------------------------
# Test 5 : Filtre par facility_ids (equipment_id)
# ---------------------------------------------------------------------------


def test_facility_ids_filter(client):
    """Seuls les résultats liés à l'équipement spécifié doivent être retournés."""
    headers = _auth(client)
    equip_a = _create_equipment(client, headers, "Analyser-EPID-A")
    equip_b = _create_equipment(client, headers, "Analyser-EPID-B")

    pid = _create_patient(client, headers, "FID-001")
    sid_a = _create_sample(client, headers, pid, "BC-FID-A-001")
    sid_b = _create_sample(client, headers, pid, "BC-FID-B-001")

    today = datetime.date.today().isoformat()
    _create_result(client, headers, sid_a, CRITICAL_DATA, equipment_id=equip_a)
    _create_result(client, headers, sid_b, NORMAL_DATA, equipment_id=equip_b)

    data_all = _dashboard(client, headers, {"start_date": today, "end_date": today})
    data_a = _dashboard(
        client, headers, {"start_date": today, "end_date": today, "facility_ids": [equip_a]}
    )

    # Filtré sur A : 1 résultat critique
    assert data_a["total_results"] == 1
    assert data_a["total_critical"] == 1
    # Sans filtre : au moins 2 résultats
    assert data_all["total_results"] >= 2


# ---------------------------------------------------------------------------
# Test 6 : Tendance journalière cohérente
# ---------------------------------------------------------------------------


def test_daily_critical_trend_coherent(client):
    """La somme des counts de la tendance journalière = total_critical."""
    headers = _auth(client)
    pid = _create_patient(client, headers, "DT-001")
    sid1 = _create_sample(client, headers, pid, "BC-DT-001")
    sid2 = _create_sample(client, headers, pid, "BC-DT-002")

    today = datetime.date.today().isoformat()
    _create_result(client, headers, sid1, CRITICAL_DATA)
    _create_result(client, headers, sid2, MIXED_DATA)

    data = _dashboard(client, headers, {"start_date": today, "end_date": today})

    trend_sum = sum(entry["count"] for entry in data["daily_critical_trend"])
    assert trend_sum == data["total_critical"], (
        f"Somme tendance {trend_sum} != total_critical {data['total_critical']}"
    )
    # Chaque entrée doit avoir 'date' et 'count'
    for entry in data["daily_critical_trend"]:
        assert "date" in entry
        assert "count" in entry


# ---------------------------------------------------------------------------
# Test 7 : 401 sans token
# ---------------------------------------------------------------------------


def test_dashboard_requires_auth(client):
    """L'endpoint doit retourner 401 sans Bearer token."""
    resp = client.post(DASHBOARD_URL, json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 8 : Réponse vide mais valide si aucun résultat dans la période
# ---------------------------------------------------------------------------


def test_empty_period_returns_valid_structure(client):
    """Si aucun résultat n'existe dans la période, la réponse doit rester valide."""
    headers = _auth(client)

    # Période très ancienne, sans données
    data = _dashboard(
        client,
        headers,
        {"start_date": "2000-01-01", "end_date": "2000-01-31"},
    )

    assert data["total_results"] == 0
    assert data["total_critical"] == 0
    assert data["overall_critical_rate"] == 0.0
    assert data["parameter_stats"] == []
    assert data["facility_stats"] == []
    assert data["daily_critical_trend"] == []
    # Les dates de période doivent être présentes
    assert data["period_start"] == "2000-01-01"
    assert data["period_end"] == "2000-01-31"


# ---------------------------------------------------------------------------
# Test 9 : Filtre par paramètres
# ---------------------------------------------------------------------------


def test_parameter_filter(client):
    """Avec parameters=['WBC'], seul WBC doit apparaître dans parameter_stats."""
    headers = _auth(client)
    pid = _create_patient(client, headers, "PF-001")
    sid = _create_sample(client, headers, pid, "BC-PF-001")
    today = datetime.date.today().isoformat()
    _create_result(client, headers, sid, NORMAL_DATA)

    data = _dashboard(
        client,
        headers,
        {"start_date": today, "end_date": today, "parameters": ["WBC"]},
    )

    params_found = [ps["parameter"] for ps in data["parameter_stats"]]
    assert "WBC" in params_found, "WBC devrait être présent"
    assert "HGB" not in params_found, "HGB ne devrait pas être présent avec le filtre"
    assert "PLT" not in params_found, "PLT ne devrait pas être présent avec le filtre"


# ---------------------------------------------------------------------------
# Test 10 : Tri décroissant de parameter_stats par critical_rate
# ---------------------------------------------------------------------------


def test_parameter_stats_sorted_by_critical_rate_desc(client):
    """parameter_stats doit être trié par critical_rate décroissant."""
    headers = _auth(client)
    pid = _create_patient(client, headers, "SORT-001")
    sid1 = _create_sample(client, headers, pid, "BC-SORT-001")
    sid2 = _create_sample(client, headers, pid, "BC-SORT-002")

    today = datetime.date.today().isoformat()
    # Un résultat avec tous critiques, un avec tous normaux
    _create_result(client, headers, sid1, CRITICAL_DATA)
    _create_result(client, headers, sid2, NORMAL_DATA)

    data = _dashboard(client, headers, {"start_date": today, "end_date": today})

    rates = [ps["critical_rate"] for ps in data["parameter_stats"]]
    assert rates == sorted(rates, reverse=True), (
        f"parameter_stats n'est pas trié par critical_rate décroissant : {rates}"
    )


# ---------------------------------------------------------------------------
# Test 11 : FacilityStats structure
# ---------------------------------------------------------------------------


def test_facility_stats_structure(client):
    """Chaque entrée facility_stats doit contenir les champs requis."""
    headers = _auth(client)
    equip = _create_equipment(client, headers, "Analyser-FSTRUCT")
    pid = _create_patient(client, headers, "FS-STRUCT-001")
    sid = _create_sample(client, headers, pid, "BC-FS-STRUCT-001")
    today = datetime.date.today().isoformat()
    _create_result(client, headers, sid, CRITICAL_DATA, equipment_id=equip)

    data = _dashboard(client, headers, {"start_date": today, "end_date": today})

    assert len(data["facility_stats"]) >= 1
    for fs in data["facility_stats"]:
        assert "facility_id" in fs
        assert "facility_name" in fs
        assert "total_results" in fs
        assert "critical_count" in fs
        assert "critical_rate" in fs


# ---------------------------------------------------------------------------
# Test 12 : Valeurs numériques correctes dans ParameterStats
# ---------------------------------------------------------------------------


def test_parameter_mean_min_max(client):
    """mean_value, min_value, max_value doivent être cohérentes avec les données insérées."""
    headers = _auth(client)
    pid = _create_patient(client, headers, "MMM-001")
    sid1 = _create_sample(client, headers, pid, "BC-MMM-001")
    sid2 = _create_sample(client, headers, pid, "BC-MMM-002")
    today = datetime.date.today().isoformat()

    # WBC : 7.2 et 1.5
    _create_result(
        client, headers, sid1, {"WBC": {"value": 7.2, "unit": "10^9/L", "status": "NORMAL"}}
    )
    _create_result(
        client, headers, sid2, {"WBC": {"value": 1.5, "unit": "10^9/L", "status": "CRITICAL_LOW"}}
    )

    data = _dashboard(
        client, headers, {"start_date": today, "end_date": today, "parameters": ["WBC"]}
    )

    wbc_stats = next((ps for ps in data["parameter_stats"] if ps["parameter"] == "WBC"), None)
    assert wbc_stats is not None, "WBC absent des parameter_stats"
    assert wbc_stats["total_results"] == 2
    assert wbc_stats["critical_count"] == 1
    assert abs(wbc_stats["critical_rate"] - 0.5) < 1e-3
    assert wbc_stats["min_value"] == pytest.approx(1.5, abs=0.01)
    assert wbc_stats["max_value"] == pytest.approx(7.2, abs=0.01)
    assert wbc_stats["mean_value"] == pytest.approx((7.2 + 1.5) / 2, abs=0.01)
