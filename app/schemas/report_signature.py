import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


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
