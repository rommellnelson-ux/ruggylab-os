"""
Tests HTTP — FHIR R4 Pharmacy Endpoints
========================================

Couverture :
  MedicationDispense
    - POST /fhir/medication-dispense  bundle structure FHIR valide
    - POST /fhir/medication-dispense  Content-Type application/fhir+json
    - POST /fhir/medication-dispense  une ressource par ligne médicament
    - POST /fhir/medication-dispense  champs patient / pharmacien / posologie
    - POST /fhir/medication-dispense  référence CMU CNAM dans note
    - POST /fhir/medication-dispense  référence autorisation prescription
    - POST /fhir/medication-dispense  status completed + codes ATC OMS
    - POST /fhir/medication-dispense  401 sans token
    - POST /fhir/medication-dispense  422 si liste vide

  SupplyDelivery
    - POST /fhir/supply-delivery      bundle structure FHIR valide
    - POST /fhir/supply-delivery      Content-Type application/fhir+json
    - POST /fhir/supply-delivery      une ressource par article livré
    - POST /fhir/supply-delivery      fournisseur / officine / date / lot
    - POST /fhir/supply-delivery      valorisation XOF dans note
    - POST /fhir/supply-delivery      référence MedicationRequest basedOn
    - POST /fhir/supply-delivery      401 sans token
    - POST /fhir/supply-delivery      422 si liste vide

  Cycle complet (intégration)
    - MedicationRequest (stock) → SupplyDelivery (livraison confirmée)
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


# ---------------------------------------------------------------------------
# Fixtures de payload
# ---------------------------------------------------------------------------

_DISPENSE_PAYLOAD = {
    "patient_ref": "IPP-CI-2026-001234",
    "practitioner_ref": "PHARM-CI-001",
    "pharmacy_id": "PHARM-ABJ-001",
    "cnam_billing_ref": "CMU-2026-FACT-9876",
    "authorizing_prescription_ref": "urn:uuid:med-req-0001",
    "drug_lines": [
        {
            "dci_code": "ARTEMETHER-LUMEFANTRINE",
            "quantity": 6,
            "dose_mg": 480.0,
            "frequency_per_day": 2,
            "duration_days": 3,
            "route": "oral",
        },
        {
            "dci_code": "PARACETAMOL",
            "quantity": 20,
            "dose_mg": 500.0,
            "frequency_per_day": 3,
            "duration_days": 5,
            "route": "oral",
        },
    ],
}

_SUPPLY_PAYLOAD = {
    "supplier_name": "NPSP Côte d'Ivoire",
    "destination_pharmacy_id": "PHARM-ABJ-001",
    "delivery_date": "2026-05-24",
    "order_reference": "urn:uuid:med-req-0001",
    "items": [
        {
            "dci_code": "ARTEMETHER-LUMEFANTRINE",
            "quantity": 500,
            "unit_cost_xof": 1000.0,
            "batch_number": "LOT-2026-ACT-042",
            "expiry_date": "2028-03-31",
        },
        {
            "dci_code": "AMOXICILLIN",
            "quantity": 1000,
            "unit_cost_xof": 150.0,
            "batch_number": "LOT-2026-AMX-019",
        },
    ],
}


# ============================================================================
# MedicationDispense — POST /api/v1/fhir/medication-dispense
# ============================================================================


def test_dispense_returns_fhir_bundle(client) -> None:
    """Le bundle retourné est une ressource FHIR Bundle de type collection."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "collection"


def test_dispense_content_type_fhir_json(client) -> None:
    """Le Content-Type doit être application/fhir+json."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    assert r.status_code == 200
    assert "application/fhir+json" in r.headers["content-type"]


def test_dispense_one_entry_per_drug_line(client) -> None:
    """Le bundle contient autant d'entrées que de lignes médicaments."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    assert body["total"] == 2
    assert len(body["entry"]) == 2


def test_dispense_resource_type_medication_dispense(client) -> None:
    """Chaque entrée contient une ressource de type MedicationDispense."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    for entry in body["entry"]:
        assert entry["resource"]["resourceType"] == "MedicationDispense"


def test_dispense_status_completed(client) -> None:
    """Le statut de chaque MedicationDispense est 'completed'."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    for entry in body["entry"]:
        assert entry["resource"]["status"] == "completed"


def test_dispense_medication_atc_code(client) -> None:
    """Le code médicament utilise le système ATC OMS."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    coding = first["medicationCodeableConcept"]["coding"]
    assert any(c["system"] == "http://www.whocc.no/atc" for c in coding)
    assert any(c["code"] == "ARTEMETHER-LUMEFANTRINE" for c in coding)


def test_dispense_patient_reference_embedded(client) -> None:
    """La référence patient est présente dans chaque MedicationDispense."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    for entry in body["entry"]:
        subject = entry["resource"].get("subject", {})
        assert "IPP-CI-2026-001234" in subject.get("reference", "")


def test_dispense_quantity_matches_request(client) -> None:
    """La quantité dispensée dans la ressource correspond à la requête."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    assert first["quantity"]["value"] == pytest.approx(6.0)


def test_dispense_cnam_billing_ref_in_note(client) -> None:
    """La référence dossier CMU CNAM apparaît dans les notes de la ressource."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    notes_text = " ".join(n["text"] for n in first.get("note", []))
    assert "CMU-2026-FACT-9876" in notes_text


def test_dispense_authorizing_prescription_ref(client) -> None:
    """La référence de prescription autorisant la dispensation est présente."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    auth_refs = first.get("authorizingPrescription", [])
    assert any("med-req-0001" in ref.get("reference", "") for ref in auth_refs)


def test_dispense_dosage_instruction_present(client) -> None:
    """La posologie (dose, fréquence, durée) est encodée en dosageInstruction."""
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=_DISPENSE_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    dosage = first.get("dosageInstruction", [])
    assert len(dosage) >= 1
    assert "480" in dosage[0].get("text", "")  # dose_mg dans le texte


def test_dispense_requires_auth(client) -> None:
    r = client.post("/api/v1/fhir/medication-dispense", json=_DISPENSE_PAYLOAD)
    assert r.status_code == 401


def test_dispense_invalid_empty_drug_lines(client) -> None:
    """422 si la liste de médicaments est vide."""
    bad = {**_DISPENSE_PAYLOAD, "drug_lines": []}
    r = client.post(
        "/api/v1/fhir/medication-dispense",
        json=bad,
        headers=_headers(client),
    )
    assert r.status_code == 422


# ============================================================================
# SupplyDelivery — POST /api/v1/fhir/supply-delivery
# ============================================================================


def test_supply_delivery_returns_fhir_bundle(client) -> None:
    """Le bundle retourné est une ressource FHIR Bundle de type collection."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "collection"


def test_supply_delivery_content_type_fhir_json(client) -> None:
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    assert r.status_code == 200
    assert "application/fhir+json" in r.headers["content-type"]


def test_supply_delivery_one_entry_per_item(client) -> None:
    """Le bundle contient autant d'entrées que d'articles livrés."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    assert body["total"] == 2
    assert len(body["entry"]) == 2


def test_supply_delivery_resource_type(client) -> None:
    """Chaque entrée contient une ressource de type SupplyDelivery."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    for entry in body["entry"]:
        assert entry["resource"]["resourceType"] == "SupplyDelivery"


def test_supply_delivery_status_completed(client) -> None:
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    for entry in body["entry"]:
        assert entry["resource"]["status"] == "completed"


def test_supply_delivery_supplied_item_present(client) -> None:
    """suppliedItem contient le code ATC + la quantité."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    supplied = first["suppliedItem"]
    assert supplied["quantity"]["value"] == pytest.approx(500.0)
    codings = supplied["itemCodeableConcept"]["coding"]
    assert any(c["code"] == "ARTEMETHER-LUMEFANTRINE" for c in codings)


def test_supply_delivery_supplier_reference(client) -> None:
    """La référence fournisseur est encodée dans supplier."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    assert "NPSP" in first["supplier"]["display"]


def test_supply_delivery_destination_reference(client) -> None:
    """La référence officine est encodée dans destination."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    assert "PHARM-ABJ-001" in first["destination"]["display"]


def test_supply_delivery_occurrence_date(client) -> None:
    """La date de livraison est présente dans occurrenceDateTime."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    assert first["occurrenceDateTime"] == "2026-05-24"


def test_supply_delivery_batch_number_in_note(client) -> None:
    """Le numéro de lot est tracé dans les notes."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    notes_text = " ".join(n["text"] for n in first.get("note", []))
    assert "LOT-2026-ACT-042" in notes_text


def test_supply_delivery_xof_valuation_in_note(client) -> None:
    """La valorisation XOF (coût × quantité) est tracée dans les notes."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    notes_text = " ".join(n["text"] for n in first.get("note", []))
    # 1000 XOF × 500 = 500000
    assert "500000" in notes_text


def test_supply_delivery_based_on_medication_request(client) -> None:
    """basedOn référence le MedicationRequest à l'origine de la commande."""
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=_SUPPLY_PAYLOAD,
        headers=_headers(client),
    )
    body = r.json()
    first = body["entry"][0]["resource"]
    based_on = first.get("basedOn", [])
    assert any("med-req-0001" in ref.get("reference", "") for ref in based_on)


def test_supply_delivery_requires_auth(client) -> None:
    r = client.post("/api/v1/fhir/supply-delivery", json=_SUPPLY_PAYLOAD)
    assert r.status_code == 401


def test_supply_delivery_invalid_empty_items(client) -> None:
    """422 si la liste d'articles livrés est vide."""
    bad = {**_SUPPLY_PAYLOAD, "items": []}
    r = client.post(
        "/api/v1/fhir/supply-delivery",
        json=bad,
        headers=_headers(client),
    )
    assert r.status_code == 422


# ============================================================================
# Cycle complet — MedicationRequest → SupplyDelivery
# ============================================================================


def test_full_cycle_medication_request_to_supply_delivery(client) -> None:
    """
    Cycle complet : StockPredictor génère un MedicationRequest bundle,
    puis SupplyDelivery confirme la réception de la commande.
    """
    h = _headers(client)

    # 1. StockPredictor → MedicationRequest (stock critique)
    predict_payload = {
        "drugs": [
            {
                "dci_code": "ARTEMETHER-LUMEFANTRINE",
                "current_stock": 10,  # stock quasi nul → rupture imminente
                "cmm_units": 100,
                "unit_cost_xof": 1000,
            }
        ],
        "horizon_days": 90,
        "include_fhir": True,
    }
    r_predict = client.post("/api/v1/stock/predict", json=predict_payload, headers=h)
    assert r_predict.status_code == 200, r_predict.text
    med_request_bundle = r_predict.json()["fhir_medication_request"]
    assert med_request_bundle is not None
    assert med_request_bundle["resourceType"] == "Bundle"

    # Récupérer l'URL FHIR de la première commande
    first_entry_url = med_request_bundle["entry"][0]["fullUrl"]

    # 2. SupplyDelivery → livraison reçue, référençant le MedicationRequest
    delivery_payload = {
        "supplier_name": "NPSP Côte d'Ivoire",
        "destination_pharmacy_id": "PHARM-ABJ-001",
        "delivery_date": "2026-05-24",
        "order_reference": first_entry_url,
        "items": [
            {
                "dci_code": "ARTEMETHER-LUMEFANTRINE",
                "quantity": 600,  # ORDER_UP_TO = 6 mois × 100 CMM = 600 - 10 stock = 590
                "unit_cost_xof": 1000.0,
                "batch_number": "LOT-2026-ACT-042",
            }
        ],
    }
    r_delivery = client.post("/api/v1/fhir/supply-delivery", json=delivery_payload, headers=h)
    assert r_delivery.status_code == 200, r_delivery.text
    delivery_bundle = r_delivery.json()

    assert delivery_bundle["resourceType"] == "Bundle"
    assert delivery_bundle["total"] == 1

    delivery_resource = delivery_bundle["entry"][0]["resource"]
    assert delivery_resource["resourceType"] == "SupplyDelivery"
    assert delivery_resource["status"] == "completed"
    # La référence MedicationRequest est tracée dans basedOn
    assert any(first_entry_url in ref["reference"] for ref in delivery_resource["basedOn"])
