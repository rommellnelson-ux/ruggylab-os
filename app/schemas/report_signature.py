import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeliveryChannel = Literal["internal", "patient_portal", "prescriber"]


def _default_delivery_channels() -> list[DeliveryChannel]:
    return ["internal"]


class ReportSignatureCreate(BaseModel):
    signature_meaning: str = Field(
        default="Validation biologique et signature electronique du rapport.",
        min_length=5,
        max_length=150,
    )


class ReportSignatureRead(BaseModel):
    id: int
    result_id: int
    signed_by_user_id: int
    report_hash: str
    signature_hash: str
    signature_meaning: str
    signed_at: dt.datetime
    revoked_at: dt.datetime | None = None
    revocation_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReportReleaseCreate(BaseModel):
    audience: Literal["clinician", "patient"] = "clinician"
    delivery_channels: list[DeliveryChannel] = Field(
        default_factory=_default_delivery_channels,
        min_length=1,
        max_length=3,
    )


class ReportSnapshotRead(BaseModel):
    id: int
    result_id: int
    version_number: int
    status: str
    audience: str
    schema_version: str
    pdf_sha256: str
    verification_path: str
    supersedes_snapshot_id: int | None = None
    created_by_user_id: int | None = None
    created_at: dt.datetime
    revoked_at: dt.datetime | None = None
    revocation_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReportSnapshotRevoke(BaseModel):
    reason: str = Field(min_length=5, max_length=250)


class ReportVerifyRead(BaseModel):
    status: Literal["valid", "provisional", "corrected", "revoked"]
    snapshot_id: int
    result_id: int
    version_number: int
    document_status: str
    created_at: dt.datetime
    pdf_sha256: str
    revoked_at: dt.datetime | None = None
