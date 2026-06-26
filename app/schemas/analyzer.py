import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalyzerResultIngest(BaseModel):
    analyzer_id: str = Field(..., min_length=1, max_length=100)
    message_id: str | None = Field(default=None, max_length=160)
    sample_barcode: str = Field(..., min_length=1, max_length=100)
    exam_code: str | None = Field(default=None, max_length=50)
    data_points: dict[str, Any] = Field(..., min_length=1)
    analysis_date: dt.datetime | None = None
    raw_message_hash: str | None = Field(default=None, max_length=128)

    model_config = ConfigDict(extra="forbid")


class AnalyzerResultIngestResponse(BaseModel):
    status: str
    result_id: int | None = None
    sample_id: int | None = None
    sample_barcode: str
    idempotency_key: str
    message: str
