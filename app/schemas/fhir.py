"""FHIR R4 DiagnosticReport schema for NFS (Numération Formule Sanguine / CBC).

Only the subset of FHIR R4 needed for CBC reporting is modelled here.
Full FHIR compliance would require the `fhir.resources` package; this
lightweight implementation produces valid R4 JSON without the extra
dependency.

Reference: https://hl7.org/fhir/R4/diagnosticreport.html
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------


class FHIRCoding(BaseModel):
    system: str
    code: str
    display: str | None = None


class FHIRCodeableConcept(BaseModel):
    coding: list[FHIRCoding] = Field(default_factory=list)
    text: str | None = None


class FHIRQuantity(BaseModel):
    value: float
    unit: str
    system: str = "http://unitsofmeasure.org"
    code: str


class FHIRReference(BaseModel):
    reference: str
    display: str | None = None


class FHIRIdentifier(BaseModel):
    system: str | None = None
    value: str


class FHIRHumanName(BaseModel):
    family: str | None = None
    given: list[str] = Field(default_factory=list)


class FHIRMeta(BaseModel):
    profile: list[str] = Field(default_factory=list)
    lastUpdated: str | None = None


class FHIRNarrative(BaseModel):
    status: str = "generated"
    div: str = "<div xmlns='http://www.w3.org/1999/xhtml'>CBC DiagnosticReport</div>"


# ---------------------------------------------------------------------------
# Contained resources
# ---------------------------------------------------------------------------


class FHIRContainedPatient(BaseModel):
    resourceType: str = "Patient"
    id: str
    identifier: list[FHIRIdentifier] = Field(default_factory=list)
    name: list[FHIRHumanName] = Field(default_factory=list)
    birthDate: str | None = None
    gender: str | None = None


class FHIRObservation(BaseModel):
    resourceType: str = "Observation"
    id: str
    status: str = "final"
    category: list[FHIRCodeableConcept] = Field(default_factory=list)
    code: FHIRCodeableConcept
    subject: FHIRReference | None = None
    effectiveDateTime: str | None = None
    valueQuantity: FHIRQuantity | None = None
    valueString: str | None = None
    valueCodeableConcept: FHIRCodeableConcept | None = None
    interpretation: list[FHIRCodeableConcept] = Field(default_factory=list)
    referenceRange: list[dict[str, Any]] = Field(default_factory=list)
    note: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DiagnosticReport (top-level resource)
# ---------------------------------------------------------------------------


class FHIRDiagnosticReport(BaseModel):
    """FHIR R4 DiagnosticReport — CBC / NFS panel."""

    resourceType: str = "DiagnosticReport"
    id: str
    meta: FHIRMeta = Field(default_factory=FHIRMeta)
    text: FHIRNarrative = Field(default_factory=FHIRNarrative)
    contained: list[FHIRContainedPatient | FHIRObservation | dict] = Field(default_factory=list)
    identifier: list[FHIRIdentifier] = Field(default_factory=list)
    status: str = "final"
    category: list[FHIRCodeableConcept] = Field(default_factory=list)
    code: FHIRCodeableConcept
    subject: FHIRReference | None = None
    effectiveDateTime: str | None = None
    issued: str | None = None
    result: list[FHIRReference] = Field(default_factory=list)
    conclusion: str | None = None
    conclusionCode: list[FHIRCodeableConcept] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# MedicationDispense — dispensation réelle à un patient
# Reference: https://hl7.org/fhir/R4/medicationdispense.html
# ---------------------------------------------------------------------------


class FHIRDosageInstruction(BaseModel):
    """Posologie simplifiée (sous-ensemble FHIR R4 Dosage)."""

    text: str | None = None
    route: FHIRCodeableConcept | None = None
    doseAndRate: list[dict] = Field(default_factory=list)


class FHIRMedicationDispense(BaseModel):
    """FHIR R4 MedicationDispense — une ligne de dispensation."""

    resourceType: str = "MedicationDispense"
    id: str
    meta: FHIRMeta = Field(default_factory=FHIRMeta)
    status: str = "completed"
    medicationCodeableConcept: FHIRCodeableConcept
    subject: FHIRReference | None = None
    performer: list[dict] = Field(default_factory=list)
    authorizingPrescription: list[FHIRReference] = Field(default_factory=list)
    quantity: FHIRQuantity | None = None
    whenHandedOver: str | None = None
    dosageInstruction: list[FHIRDosageInstruction] = Field(default_factory=list)
    note: list[dict[str, str]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# SupplyDelivery — livraison d'un réassort à une officine
# Reference: https://hl7.org/fhir/R4/supplydelivery.html
# ---------------------------------------------------------------------------


class FHIRSupplyDelivery(BaseModel):
    """FHIR R4 SupplyDelivery — une ligne de livraison de stock."""

    resourceType: str = "SupplyDelivery"
    id: str
    meta: FHIRMeta = Field(default_factory=FHIRMeta)
    status: str = "completed"
    type: FHIRCodeableConcept | None = None
    suppliedItem: dict | None = None  # { quantity, itemCodeableConcept }
    occurrenceDateTime: str | None = None
    supplier: FHIRReference | None = None
    destination: FHIRReference | None = None
    basedOn: list[FHIRReference] = Field(default_factory=list)
    note: list[dict[str, str]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Requêtes d'entrée — MedicationDispense
# ---------------------------------------------------------------------------


class DispenseLineRequest(BaseModel):
    """Ligne de dispensation (un médicament DCI)."""

    dci_code: str = Field(min_length=2, examples=["ARTEMETHER-LUMEFANTRINE"])
    quantity: int = Field(gt=0, description="Unités dispensées")
    dose_mg: float | None = Field(default=None, description="Dose par prise (mg)")
    frequency_per_day: int | None = Field(default=None, ge=1, le=24)
    duration_days: int | None = Field(default=None, ge=1)
    route: str = Field(default="oral", description="Voie d'administration")

    @field_validator("dci_code")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.strip().upper()


class MedicationDispenseRequest(BaseModel):
    """
    Requête de génération d'un bundle FHIR MedicationDispense.

    Représente une dispensation complète (ordonnance validée + acte pharmacien).
    Chaque ligne produit un MedicationDispense distinct dans le bundle.
    """

    patient_ref: str = Field(
        description="Référence patient (IPP ou identifiant interne)",
        examples=["IPP-CI-2026-001234"],
    )
    practitioner_ref: str | None = Field(
        default=None,
        description="Référence pharmacien/prescripteur",
    )
    pharmacy_id: str | None = Field(
        default=None,
        description="Identifiant officine (CNPS ou code interne)",
    )
    dispensed_at: str | None = Field(
        default=None,
        description="Date/heure ISO-8601 de dispensation (défaut : maintenant)",
    )
    drug_lines: list[DispenseLineRequest] = Field(
        min_length=1,
        description="Médicaments dispensés (une entrée par DCI)",
    )
    authorizing_prescription_ref: str | None = Field(
        default=None,
        description="Référence du MedicationRequest FHIR autorisant la dispensation",
    )
    cnam_billing_ref: str | None = Field(
        default=None,
        description="Numéro de dossier de facturation CMU (traçabilité CNAM)",
    )


# ---------------------------------------------------------------------------
# Requêtes d'entrée — SupplyDelivery
# ---------------------------------------------------------------------------


class SupplyItemRequest(BaseModel):
    """Ligne d'article livré (un médicament DCI)."""

    dci_code: str = Field(min_length=2, examples=["ARTEMETHER-LUMEFANTRINE"])
    quantity: int = Field(gt=0, description="Unités livrées")
    unit_cost_xof: float | None = Field(
        default=None,
        gt=0,
        description="Coût unitaire XOF (pour valorisation du stock)",
    )
    batch_number: str | None = Field(default=None, description="Numéro de lot")
    expiry_date: str | None = Field(default=None, description="Date de péremption (ISO-8601)")

    @field_validator("dci_code")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.strip().upper()


class SupplyDeliveryRequest(BaseModel):
    """
    Requête de génération d'un bundle FHIR SupplyDelivery.

    Représente la réception d'une livraison de médicaments en officine
    suite à une commande de réassort (générée par StockPredictor).
    """

    supplier_name: str = Field(
        description="Nom du fournisseur (grossiste ou NPSP/CSST)",
        examples=["NPSP Côte d'Ivoire"],
    )
    destination_pharmacy_id: str = Field(
        description="Identifiant de l'officine destinataire",
        examples=["PHARM-ABJ-001"],
    )
    delivery_date: str | None = Field(
        default=None,
        description="Date de livraison ISO-8601 (défaut : aujourd'hui)",
    )
    items: list[SupplyItemRequest] = Field(
        min_length=1,
        description="Articles livrés",
    )
    order_reference: str | None = Field(
        default=None,
        description="Référence du MedicationRequest FHIR ayant déclenché la commande",
    )
