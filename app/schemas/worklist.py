import datetime as dt

from pydantic import BaseModel, Field


class WorklistAction(BaseModel):
    label: str
    method: str = "GET"
    path: str
    style: str = "primary"


class WorklistItem(BaseModel):
    id: str
    category: str
    priority: str
    title: str
    subtitle: str | None = None
    status: str
    due_at: dt.datetime | None = None
    elapsed_minutes: int | None = None
    unit: str | None = None
    actions: list[WorklistAction] = Field(default_factory=list)


class WorklistSummary(BaseModel):
    total: int = 0
    critical: int = 0
    overdue: int = 0
    urgent: int = 0
    blocked: int = 0


class WorklistResponse(BaseModel):
    generated_at: dt.datetime
    summary: WorklistSummary
    items: list[WorklistItem] = Field(default_factory=list)
