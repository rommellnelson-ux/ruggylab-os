"""
Tests HTTP — Endpoints CMU (Billing, Stock Predictor, Prescription Scanner)
===========================================================================

Couverture :
  Billing
    - POST /billing/calculate  assuré 70/30
    - POST /billing/calculate  non-assuré + remise générique
    - POST /billing/calculate  400 si payload invalide
    - POST /billing/cmm-report rapport CMM trié par criticité
  Stock Predictor
    - POST /stock/predict      prédiction horizon 90 j
    - POST /stock/cmm-history  CMM calculé depuis historique mensuel
  Prescription Scanner
    - POST /prescription/scan  ordonnance valide → VALID
    - POST /prescription/scan  ARTEMETHER + HALOFANTRINE → BLOCKED
    - POST /prescription/interactions  paire contradictée détectée
    - 401 sur chaque endpoint sans token
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, username: str = "admin", password: str = "change_me_admin_password") -> str:
    r = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client)}"}


# ============================================================================
# Billing — POST /api/v1/billing/calculate
# ============================================================================

_INSURED_PAYLOAD = {
    "patient_type": "INSURED",
    "insurance_id": "CNAM-CI-2026-TEST",
    "diagnoses": [{"cim10": {"code": "B54"}, "is_primary": True}],
    "drugs": [
        {
            "dci": {"code": "ARTEMETHER-LUMEFANTRINE"},
            "quantity": 6,
            "unit_price_xof": "1000",
            "is_generic": False,
        }
    ],
    "payment_method": "INSURANCE",
}

_UNINSURED_PAYLOAD = {
    "patient_type": "UNINSURED",
    "diagnoses": [{"cim10": {"code": "B54"}, "is_primary": True}],
    "drugs": [
        {
            "dci": {"code": "ARTEMETHER-LUMEFANTRINE"},
            "quantity": 6,
            "unit_price_xof": "1000",
            "is_generic": True,
        }
    ],
    "payment_method": "CASH",
    "discount_program": "GENERIC_SUBSTITUTION",
}


def test_billing_calculate_insured_70_30(client) -> None:
    """Répartition CNAM 70 % / ticket 30 % sur patient assuré."""
    r = client.post(
        "/api/v1/billing/calculate",
        json=_INSURED_PAYLOAD,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["patient_type"] == "INSURED"
    assert float(body["net_total_xof"]) == pytest.approx(6000.0)
    assert float(body["cnam_coverage_xof"]) == pytest.approx(4200.0)  # 70 %
    assert float(body["patient_due_xof"]) == pytest.approx(1800.0)  # 30 %


def test_billing_calculate_uninsured_generic_discount(client) -> None:
    """Non-assuré + programme générique → remise 20 % sur la ligne générique."""
    r = client.post(
        "/api/v1/billing/calculate",
        json=_UNINSURED_PAYLOAD,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["patient_type"] == "UNINSURED"
    assert float(body["cnam_coverage_xof"]) == pytest.approx(0.0)
    # 6 × 1000 × (1 - 0.20) = 4800
    assert float(body["net_total_xof"]) == pytest.approx(4800.0)
    assert float(body["patient_due_xof"]) == pytest.approx(4800.0)


def test_billing_calculate_requires_auth(client) -> None:
    """401 sans token."""
    r = client.post("/api/v1/billing/calculate", json=_INSURED_PAYLOAD)
    assert r.status_code == 401


def test_billing_calculate_invalid_payload(client) -> None:
    """422 si la liste de médicaments est vide."""
    bad = {**_INSURED_PAYLOAD, "drugs": []}
    r = client.post("/api/v1/billing/calculate", json=bad, headers=_headers(client))
    assert r.status_code == 422


# ============================================================================
# Billing — POST /api/v1/billing/cmm-report
# ============================================================================


def test_billing_cmm_report_sorted_by_criticality(client) -> None:
    """Les médicaments critiques (stock < 2 mois) sortent en tête de rapport."""
    payload = {
        "entries": [
            {"dci_code": "AMOXICILLIN", "cmm_units": 100, "current_stock": 500},  # ok
            {
                "dci_code": "ARTEMETHER-LUMEFANTRINE",
                "cmm_units": 200,
                "current_stock": 50,
            },  # critique
        ]
    }
    r = client.post(
        "/api/v1/billing/cmm-report",
        json=payload,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    entries = r.json()
    assert len(entries) == 2
    # Le critique (< 2 mois) doit apparaître en premier
    assert entries[0]["dci_code"] == "ARTEMETHER-LUMEFANTRINE"
    assert entries[0]["months_of_stock"] < 2.0


def test_billing_cmm_report_requires_auth(client) -> None:
    r = client.post("/api/v1/billing/cmm-report", json={"entries": []})
    assert r.status_code == 401


# ============================================================================
# Stock Predictor — POST /api/v1/stock/predict
# ============================================================================

_STOCK_PAYLOAD = {
    "drugs": [
        {
            "dci_code": "ARTEMETHER-LUMEFANTRINE",
            "current_stock": 500,
            "cmm_units": 100,
            "unit_cost_xof": 1000,
        },
        {
            "dci_code": "PARACETAMOL",
            "current_stock": 200,
            "cmm_units": 80,
            "unit_cost_xof": 200,
        },
    ],
    "horizon_days": 90,
    "include_fhir": False,
}


def test_stock_predict_returns_result(client) -> None:
    """Prédiction 90 jours — champs obligatoires présents."""
    r = client.post(
        "/api/v1/stock/predict",
        json=_STOCK_PAYLOAD,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_drugs"] == 2
    assert body["horizon_days"] == 90
    assert "critical_count" in body
    assert "drug_predictions" in body
    assert len(body["drug_predictions"]) == 2


def test_stock_predict_fhir_bundle_when_requested(client) -> None:
    """Avec include_fhir=True et stock critique, le bundle FHIR est présent."""
    payload = {**_STOCK_PAYLOAD, "include_fhir": True}
    # Force un stock critique
    payload["drugs"] = [
        {
            "dci_code": "ARTEMETHER-LUMEFANTRINE",
            "current_stock": 10,  # stock quasi nul → rupture imminente
            "cmm_units": 100,
            "unit_cost_xof": 1000,
        }
    ]
    r = client.post(
        "/api/v1/stock/predict",
        json=payload,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fhir_medication_request"] is not None
    assert body["fhir_medication_request"]["resourceType"] == "Bundle"


def test_stock_predict_requires_auth(client) -> None:
    r = client.post("/api/v1/stock/predict", json=_STOCK_PAYLOAD)
    assert r.status_code == 401


# ============================================================================
# Stock Predictor — POST /api/v1/stock/cmm-history
# ============================================================================


def test_stock_cmm_history_calculation(client) -> None:
    """CMM calculé depuis 5 mois d'historique (mois nuls exclus)."""
    payload = {
        "dci_code": "PARACETAMOL",
        "monthly_consumptions": [100.0, 120.0, 0.0, 110.0, 130.0],  # 0 exclu
    }
    r = client.post(
        "/api/v1/stock/cmm-history",
        json=payload,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["dci_code"] == "PARACETAMOL"
    assert body["months_of_data"] == 5
    assert body["excluded_zero_months"] == 1
    # (100+120+110+130) / 4 = 115 → arrondi sup = 115
    assert body["cmm_computed"] == 115


def test_stock_cmm_requires_auth(client) -> None:
    r = client.post(
        "/api/v1/stock/cmm-history",
        json={"dci_code": "X", "monthly_consumptions": [100.0, 120.0]},
    )
    assert r.status_code == 401


# ============================================================================
# Prescription Scanner — POST /api/v1/prescription/scan
# ============================================================================

_VALID_PRESCRIPTION = {
    "diagnoses": [{"code": "B54"}],
    "drugs": [
        {
            "dci": {"code": "ARTEMETHER-LUMEFANTRINE"},
            "dose_mg": 480.0,
            "frequency_per_day": 2,
            "duration_days": 3,
            "route": "oral",
        }
    ],
    "patient": {
        "age_years": 35.0,
        "sex": "M",
        "is_pregnant": False,
        "has_renal_impairment": False,
        "has_hepatic_impairment": False,
        "has_g6pd_deficiency": False,
    },
}

_BLOCKED_PRESCRIPTION = {
    **_VALID_PRESCRIPTION,
    "drugs": [
        {"dci": {"code": "ARTEMETHER-LUMEFANTRINE"}, "route": "oral"},
        {"dci": {"code": "HALOFANTRINE"}, "route": "oral"},  # QT contraindication
    ],
}


def test_prescription_scan_valid_returns_valid(client) -> None:
    """Ordonnance sans interaction → statut VALID."""
    r = client.post(
        "/api/v1/prescription/scan",
        json=_VALID_PRESCRIPTION,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "VALID"
    assert body["confidence_score"] > 0


def test_prescription_scan_contraindication_blocks(client) -> None:
    """ARTEMETHER + HALOFANTRINE (QT) → statut BLOCKED."""
    r = client.post(
        "/api/v1/prescription/scan",
        json=_BLOCKED_PRESCRIPTION,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "BLOCKED"
    assert body["interaction_count"] >= 1


def test_prescription_scan_requires_auth(client) -> None:
    r = client.post("/api/v1/prescription/scan", json=_VALID_PRESCRIPTION)
    assert r.status_code == 401


# ============================================================================
# Prescription Scanner — POST /api/v1/prescription/interactions
# ============================================================================


def test_prescription_interactions_detects_contraindication(client) -> None:
    """AMIODARONE + QUININE → CONTRAINDICATED détecté."""
    payload = {"dci_codes": ["AMIODARONE", "QUININE"]}
    r = client.post(
        "/api/v1/prescription/interactions",
        json=payload,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_contraindicated"] is True
    assert body["interaction_count"] >= 1


def test_prescription_interactions_safe_pair(client) -> None:
    """PARACETAMOL + AMOXICILLIN → aucune interaction."""
    payload = {"dci_codes": ["PARACETAMOL", "AMOXICILLIN"]}
    r = client.post(
        "/api/v1/prescription/interactions",
        json=payload,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["interaction_count"] == 0
    assert body["has_contraindicated"] is False
    assert body["has_major"] is False


def test_prescription_interactions_requires_minimum_two_drugs(client) -> None:
    """422 si moins de 2 DCI fournis."""
    payload = {"dci_codes": ["PARACETAMOL"]}
    r = client.post(
        "/api/v1/prescription/interactions",
        json=payload,
        headers=_headers(client),
    )
    assert r.status_code == 422


def test_prescription_interactions_requires_auth(client) -> None:
    r = client.post(
        "/api/v1/prescription/interactions",
        json={"dci_codes": ["A", "B"]},
    )
    assert r.status_code == 401
