"""Contrats neutres pour une future interopérabilité avec CSA PLATEAU."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CSAPatientContract(BaseModel):
    """Identité minimale échangée après accord institutionnel."""

    source_patient_id: str = Field(min_length=1, max_length=100)
    family_name: str = Field(min_length=1, max_length=100)
    given_names: str = Field(min_length=1, max_length=150)
    birth_date: dt.date
    sex: Literal["M", "F", "U"]
    phone: str | None = Field(default=None, max_length=30)
    model_config = ConfigDict(extra="forbid")


class CSAPrescribedExam(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    display: str | None = Field(default=None, max_length=150)
    coding_system: Literal["local", "LOINC"] = "local"
    model_config = ConfigDict(extra="forbid")


class CSAPrescriptionContract(BaseModel):
    source_prescription_id: str = Field(min_length=1, max_length=100)
    source_patient_id: str = Field(min_length=1, max_length=100)
    ordered_at: dt.datetime
    prescriber: str | None = Field(default=None, max_length=150)
    requesting_service: str | None = Field(default=None, max_length=100)
    priority: Literal["routine", "urgent", "stat"] = "routine"
    exams: list[CSAPrescribedExam] = Field(min_length=1, max_length=100)
    model_config = ConfigDict(extra="forbid")


class CSAContractTestRequest(BaseModel):
    """Payload de recette locale. Il n'est jamais envoyé sur le réseau."""

    patient: CSAPatientContract
    prescription: CSAPrescriptionContract
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=120)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def patient_links_match(self) -> CSAContractTestRequest:
        if self.patient.source_patient_id != self.prescription.source_patient_id:
            raise ValueError("La prescription ne référence pas le patient du contrat.")
        return self


class CSAContractTestResponse(BaseModel):
    valid: bool
    idempotency_key: str
    replayed: bool
    network_call_performed: Literal[False] = False
    patient_exchange_performed: Literal[False] = False


class CSAIntegrationStatus(BaseModel):
    enabled: bool
    patient_exchange_enabled: bool
    base_url_configured: bool
    transport_available: bool = False
    operational: bool = False
    reason: str


class CSAExamMappingCreate(BaseModel):
    csa_exam_code: str = Field(min_length=1, max_length=50)
    ruggylab_exam_code: str = Field(min_length=1, max_length=50)
    active: bool = True


class CSAExamMappingRead(CSAExamMappingCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class CSASyncSummary(BaseModel):
    received: int
    imported: int
    replayed: int
    rejected: list[dict] = Field(default_factory=list)


class CSAResultPushResponse(BaseModel):
    result_id: int
    external_event_key: str
    replayed: bool = False
