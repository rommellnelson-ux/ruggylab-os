import datetime as dt

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    id: int
    user_id: int | None = None
    event_type: str
    entity_type: str
    entity_id: str | None = None
    payload: str | None = None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)
