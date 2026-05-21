"""FHIR R4 DiagnosticReport schema for NFS (Numération Formule Sanguine / CBC).

Only the subset of FHIR R4 needed for CBC reporting is modelled here.
Full FHIR compliance would require the `fhir.resources` package; this
lightweight implementation produces valid R4 JSON without the extra
dependency.

Reference: https://hl7.org/fhir/R4/diagnosticreport.html
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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
    contained: list[FHIRContainedPatient | FHIRObservation | dict] = Field(
        default_factory=list
    )
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
