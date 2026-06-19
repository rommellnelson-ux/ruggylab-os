import datetime as dt

from pydantic import BaseModel, Field


class BenchPatientContext(BaseModel):
    id: int | None = None
    ipp: str | None = None
    display_name: str | None = None
    unit: str | None = None


class BenchSampleContext(BaseModel):
    id: int
    barcode: str
    status: str | None = None


class BenchCriticalItem(BaseModel):
    result_id: int
    exam_code: str | None = None
    analysis_date: dt.datetime | None = None
    patient: BenchPatientContext | None = None
    sample: BenchSampleContext
    analytes: list[str] = Field(default_factory=list)
    message: str


class BenchTatItem(BaseModel):
    result_id: int
    exam_code: str
    target_minutes: int
    elapsed_minutes: float
    remaining_minutes: float
    due_at: dt.datetime
    patient: BenchPatientContext | None = None
    sample: BenchSampleContext


class BenchRoutineItem(BaseModel):
    result_id: int
    exam_code: str | None = None
    analysis_date: dt.datetime | None = None
    patient: BenchPatientContext | None = None
    sample: BenchSampleContext
    analytes: list[str] = Field(default_factory=list)


class BenchRadarResponse(BaseModel):
    generated_at: dt.datetime
    criticals: list[BenchCriticalItem] = Field(default_factory=list)
    tat_expiring: list[BenchTatItem] = Field(default_factory=list)
    routine: list[BenchRoutineItem] = Field(default_factory=list)
