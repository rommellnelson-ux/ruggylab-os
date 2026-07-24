from __future__ import annotations

import datetime as dt
import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _EquipmentInputModel(BaseModel):
    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def normalize_string_fields(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    model_config = ConfigDict(extra="forbid")


class EquipmentInterfaceType(StrEnum):
    SERIAL = "serial"
    USB_DEVICE = "usb_device"
    USB_STORAGE = "usb_storage"
    ETHERNET = "ethernet"
    FILE_IMPORT = "file_import"
    MANUAL = "manual"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


class EquipmentInterfaceDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BIDIRECTIONAL = "bidirectional"
    UNKNOWN = "unknown"


class EquipmentQualificationStatus(StrEnum):
    UNQUALIFIED = "unqualified"
    DOCUMENTATION_PENDING = "documentation_pending"
    TECHNICAL_TESTING = "technical_testing"
    TECHNICALLY_QUALIFIED = "technically_qualified"
    CLINICAL_REVIEW_PENDING = "clinical_review_pending"
    CLINICALLY_APPROVED = "clinically_approved"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    RETIRED = "retired"


class EquipmentReadinessStatus(StrEnum):
    UNQUALIFIED = "unqualified"
    DOCUMENTATION_MISSING = "documentation_missing"
    TECHNICAL_TESTING = "technical_testing"
    CLINICAL_APPROVAL_REQUIRED = "clinical_approval_required"
    SUSPENDED = "suspended"
    QUALIFIED_DISABLED = "qualified_disabled"
    ENABLED = "enabled"


class EquipmentActionReasonCode(StrEnum):
    MANUAL = "manual"
    INCIDENT = "incident"
    MAINTENANCE = "maintenance"
    QUALIFICATION_EXPIRED = "qualification_expired"
    FIRMWARE_REPLACEMENT = "firmware_replacement"
    DRIVER_CHANGE = "driver_change"
    PROTOCOL_CHANGE = "protocol_change"
    CONFIGURATION_CHANGE = "configuration_change"
    RETIREMENT = "retirement"
    GOVERNANCE_DECISION = "governance_decision"


def _reject_sensitive_reference(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    forbidden_fragments = (
        "://",
        "\\\\",
        "/dev/",
        "password=",
        "passwd=",
        "token=",
        "secret=",
        "apikey=",
        "api_key=",
    )
    if any(fragment in lowered for fragment in forbidden_fragments):
        raise ValueError("Only an opaque, redacted external reference is accepted")
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?", normalized):
        raise ValueError("A real network address cannot be stored")
    if re.fullmatch(r"(?i)COM\d+", normalized):
        raise ValueError("A real serial port cannot be stored")
    return normalized


def _reject_null_update(value: object) -> object:
    if value is None:
        raise ValueError("This required field cannot be set to null")
    return value


class EquipmentBase(_EquipmentInputModel):
    name: str = Field(..., min_length=1, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    last_calibration: dt.date | None = None
    manufacturer: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    device_family: str | None = Field(default=None, max_length=100)
    firmware_version: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=100)
    clinical_use: bool = False
    lifecycle_status: str | None = Field(default=None, max_length=50)
    asset_identifier: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def reject_future_calibration(self) -> Self:
        if self.last_calibration and self.last_calibration > dt.date.today():
            raise ValueError("last_calibration cannot be in the future")
        return self


class EquipmentCreate(EquipmentBase):
    model_config = ConfigDict(extra="forbid")


class EquipmentIdentityUpdate(_EquipmentInputModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    last_calibration: dt.date | None = None
    manufacturer: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    device_family: str | None = Field(default=None, max_length=100)
    firmware_version: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=100)
    clinical_use: bool | None = None
    lifecycle_status: str | None = Field(default=None, max_length=50)
    asset_identifier: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def reject_future_calibration(self) -> Self:
        if self.last_calibration and self.last_calibration > dt.date.today():
            raise ValueError("last_calibration cannot be in the future")
        return self

    _validate_required_fields = field_validator("name", "clinical_use")(_reject_null_update)
    model_config = ConfigDict(extra="forbid")


class EquipmentSimpleRead(BaseModel):
    id: int
    name: str
    type: str | None
    device_family: str | None
    location: str | None
    unit: str | None
    lifecycle_status: str | None
    clinical_use: bool
    readiness_status: EquipmentReadinessStatus
    missing_condition_categories: list[str]


class EquipmentDetailRead(BaseModel):
    id: int
    name: str
    serial_number_masked: str | None
    type: str | None
    location: str | None
    last_calibration: dt.date | None
    manufacturer: str | None
    model: str | None
    device_family: str | None
    firmware_version: str | None
    unit: str | None
    clinical_use: bool
    lifecycle_status: str | None
    asset_identifier: str | None
    updated_at: dt.datetime | None


class EquipmentInterfaceCreate(_EquipmentInputModel):
    interface_type: EquipmentInterfaceType
    direction: EquipmentInterfaceDirection
    endpoint_reference: str | None = Field(default=None, max_length=255)
    protocol_name: str | None = Field(default=None, max_length=100)
    protocol_version: str | None = Field(default=None, max_length=100)
    driver_name: str | None = Field(default=None, max_length=100)
    driver_version: str | None = Field(default=None, max_length=100)
    configuration_version: str | None = Field(default=None, max_length=100)

    _validate_reference = field_validator("endpoint_reference")(_reject_sensitive_reference)
    model_config = ConfigDict(extra="forbid")


class EquipmentInterfaceUpdate(_EquipmentInputModel):
    interface_type: EquipmentInterfaceType | None = None
    direction: EquipmentInterfaceDirection | None = None
    endpoint_reference: str | None = Field(default=None, max_length=255)
    protocol_name: str | None = Field(default=None, max_length=100)
    protocol_version: str | None = Field(default=None, max_length=100)
    driver_name: str | None = Field(default=None, max_length=100)
    driver_version: str | None = Field(default=None, max_length=100)
    configuration_version: str | None = Field(default=None, max_length=100)
    archived: bool | None = None

    _validate_reference = field_validator("endpoint_reference")(_reject_sensitive_reference)
    _validate_required_fields = field_validator(
        "interface_type",
        "direction",
        "archived",
    )(_reject_null_update)
    model_config = ConfigDict(extra="forbid")


class EquipmentInterfaceRead(BaseModel):
    id: int
    equipment_id: int
    stable_identifier: str
    interface_type: EquipmentInterfaceType
    direction: EquipmentInterfaceDirection
    endpoint_reference_masked: str | None
    protocol_name: str | None
    protocol_version: str | None
    driver_name: str | None
    driver_version: str | None
    configuration_version: str | None
    enabled: bool
    archived: bool
    created_at: dt.datetime
    updated_at: dt.datetime | None
    disabled_at: dt.datetime | None
    disable_reason: str | None


class EquipmentQualificationDraftCreate(_EquipmentInputModel):
    equipment_interface_id: int = Field(..., ge=1)
    scope_description: str = Field(..., min_length=1, max_length=2000)
    expires_at: dt.datetime | None = None
    decision_reference: str | None = Field(default=None, max_length=255)
    evidence_reference: str | None = Field(default=None, max_length=255)
    non_clinical_comment: str | None = Field(default=None, max_length=2000)
    document_ids: list[int] = Field(default_factory=list, max_length=100)

    _validate_decision = field_validator("decision_reference")(_reject_sensitive_reference)
    _validate_evidence = field_validator("evidence_reference")(_reject_sensitive_reference)
    model_config = ConfigDict(extra="forbid")


class EquipmentQualificationDraftUpdate(_EquipmentInputModel):
    scope_description: str | None = Field(default=None, min_length=1, max_length=2000)
    expires_at: dt.datetime | None = None
    decision_reference: str | None = Field(default=None, max_length=255)
    evidence_reference: str | None = Field(default=None, max_length=255)
    non_clinical_comment: str | None = Field(default=None, max_length=2000)
    document_ids: list[int] | None = Field(default=None, max_length=100)

    _validate_decision = field_validator("decision_reference")(_reject_sensitive_reference)
    _validate_evidence = field_validator("evidence_reference")(_reject_sensitive_reference)
    _validate_scope = field_validator("scope_description")(_reject_null_update)
    model_config = ConfigDict(extra="forbid")


class EquipmentQualificationNewVersion(_EquipmentInputModel):
    scope_description: str = Field(..., min_length=1, max_length=2000)
    expires_at: dt.datetime | None = None
    decision_reference: str | None = Field(default=None, max_length=255)
    evidence_reference: str | None = Field(default=None, max_length=255)
    non_clinical_comment: str | None = Field(default=None, max_length=2000)
    document_ids: list[int] = Field(default_factory=list, max_length=100)

    _validate_decision = field_validator("decision_reference")(_reject_sensitive_reference)
    _validate_evidence = field_validator("evidence_reference")(_reject_sensitive_reference)
    model_config = ConfigDict(extra="forbid")


class EquipmentQualificationTechnicalTransition(_EquipmentInputModel):
    status: EquipmentQualificationStatus

    @field_validator("status")
    @classmethod
    def restrict_to_technical_statuses(
        cls, value: EquipmentQualificationStatus
    ) -> EquipmentQualificationStatus:
        allowed = {
            EquipmentQualificationStatus.DOCUMENTATION_PENDING,
            EquipmentQualificationStatus.TECHNICAL_TESTING,
            EquipmentQualificationStatus.TECHNICALLY_QUALIFIED,
        }
        if value not in allowed:
            raise ValueError("Only a technical draft status is accepted")
        return value

    model_config = ConfigDict(extra="forbid")


class EquipmentApprovedAnalyteCreate(_EquipmentInputModel):
    analyte_code: str = Field(..., min_length=1, max_length=100)
    method_code: str = Field(..., min_length=1, max_length=100)
    sample_type: str = Field(..., min_length=1, max_length=100)
    unit: str = Field(..., min_length=1, max_length=100)
    usage_context: str | None = Field(default=None, max_length=100)
    clinical_catalog_reference: str | None = Field(default=None, max_length=255)
    metadata_version: str | None = Field(default=None, max_length=100)

    _validate_catalog = field_validator("clinical_catalog_reference")(_reject_sensitive_reference)
    model_config = ConfigDict(extra="forbid")


class EquipmentApprovedAnalyteUpdate(_EquipmentInputModel):
    active: bool

    model_config = ConfigDict(extra="forbid")


class EquipmentApprovedAnalyteRead(BaseModel):
    id: int
    qualification_id: int
    analyte_code: str
    method_code: str
    sample_type: str
    unit: str
    usage_context: str | None
    clinical_catalog_reference: str | None
    active: bool
    metadata_version: str | None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class EquipmentQualificationRead(BaseModel):
    id: int
    equipment_id: int
    equipment_interface_id: int
    version: int
    status: EquipmentQualificationStatus
    scope_description: str
    decision_reference: str | None
    evidence_reference: str | None
    document_ids_snapshot: list[int]
    effective_at: dt.datetime | None
    expires_at: dt.datetime | None
    created_by_user_id: int | None
    approved_at: dt.datetime | None
    submitted_at: dt.datetime | None
    suspended_at: dt.datetime | None
    suspension_reason: str | None
    superseded_by_id: int | None
    archived: bool
    created_at: dt.datetime
    analytes: list[EquipmentApprovedAnalyteRead]

    model_config = ConfigDict(from_attributes=True)


class EquipmentDocumentCreate(_EquipmentInputModel):
    document_title: str = Field(..., min_length=1, max_length=255)
    document_type: str = Field(..., min_length=1, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    version: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=50)
    document_date: dt.date | None = None
    page_count: int | None = Field(default=None, ge=1, le=100_000)
    physical_copy_available: bool = False
    digital_copy_available: bool = False
    storage_reference: str | None = Field(default=None, max_length=255)
    contains_connectivity_section: bool = False
    contains_protocol_specification: bool = False
    review_status: str | None = Field(default=None, max_length=50)
    review_date: dt.date | None = None
    checksum: str | None = Field(default=None, min_length=32, max_length=128)

    _validate_storage = field_validator("storage_reference")(_reject_sensitive_reference)
    model_config = ConfigDict(extra="forbid")


class EquipmentDocumentUpdate(_EquipmentInputModel):
    document_title: str | None = Field(default=None, min_length=1, max_length=255)
    document_type: str | None = Field(default=None, min_length=1, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    version: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=50)
    document_date: dt.date | None = None
    page_count: int | None = Field(default=None, ge=1, le=100_000)
    physical_copy_available: bool | None = None
    digital_copy_available: bool | None = None
    storage_reference: str | None = Field(default=None, max_length=255)
    contains_connectivity_section: bool | None = None
    contains_protocol_specification: bool | None = None
    review_status: str | None = Field(default=None, max_length=50)
    review_date: dt.date | None = None
    checksum: str | None = Field(default=None, min_length=32, max_length=128)
    archive: bool | None = None

    _validate_storage = field_validator("storage_reference")(_reject_sensitive_reference)
    _validate_required_fields = field_validator(
        "document_title",
        "document_type",
        "physical_copy_available",
        "digital_copy_available",
        "contains_connectivity_section",
        "contains_protocol_specification",
    )(_reject_null_update)
    model_config = ConfigDict(extra="forbid")


class EquipmentDocumentRead(BaseModel):
    id: int
    equipment_id: int
    document_title: str
    document_type: str
    manufacturer: str | None
    model: str | None
    version: str | None
    language: str | None
    document_date: dt.date | None
    page_count: int | None
    physical_copy_available: bool
    digital_copy_available: bool
    storage_reference_masked: str | None
    contains_connectivity_section: bool
    contains_protocol_specification: bool
    review_status: str | None
    review_date: dt.date | None
    checksum_present: bool
    archived_at: dt.datetime | None
    created_at: dt.datetime


class EquipmentActionReason(_EquipmentInputModel):
    reason: EquipmentActionReasonCode

    model_config = ConfigDict(extra="forbid")


class EquipmentReadinessRead(BaseModel):
    equipment_id: int
    interface_id: int
    activatable: bool
    enabled: bool
    readiness_status: EquipmentReadinessStatus
    satisfied_conditions: list[str]
    missing_conditions: list[str]
    active_qualification_id: int | None
    active_qualification_version: int | None
    qualification_expires_at: dt.datetime | None
    configuration_version: str | None
    driver_name: str | None
    driver_version: str | None
    protocol_name: str | None
    protocol_version: str | None
