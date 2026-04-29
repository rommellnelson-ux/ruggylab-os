import datetime as dt

from pydantic import BaseModel, Field


class DH36IngestRequest(BaseModel):
    raw_message: str = Field(..., min_length=10)


class DH36IngestResponse(BaseModel):
    message_id: int
    status: str
    result_id: int | None = None
    sample_barcode: str | None = None
    message_control_id: str | None = None
    rejection_reason: str | None = None
    processed_at: dt.datetime | None = None
