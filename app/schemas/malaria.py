import datetime as dt

from pydantic import BaseModel, ConfigDict


class MalariaAnalysisRead(BaseModel):
    id: int
    result_id: int
    requested_by_user_id: int | None = None
    status: str
    model_name: str
    image_url: str
    prediction_label: str | None = None
    confidence: float | None = None
    error_message: str | None = None
    queued_at: dt.datetime
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None

    model_config = ConfigDict(from_attributes=True)
