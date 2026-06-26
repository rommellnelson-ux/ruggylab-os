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


class BenchPreanalytics(BaseModel):
    sample_type: str | None = None
    container: str | None = None
    collection_condition: str | None = None
    transport_delay_minutes: int | None = None
    bench: str | None = None
    patient_instruction: str | None = None
    quality_note: str | None = None


class BenchTechnicalSheet(BaseModel):
    summary: str | None = None
    source: str | None = None
    key_steps: list[str] = Field(default_factory=list)
    qc_requirements: list[str] = Field(default_factory=list)
    common_rejection_reasons: list[str] = Field(default_factory=list)


class BenchExamGuidance(BaseModel):
    label: str | None = None
    category: str | None = None
    preanalytics: BenchPreanalytics | None = None
    technical_sheet: BenchTechnicalSheet | None = None


class BenchCriticalItem(BaseModel):
    result_id: int
    exam_code: str | None = None
    analysis_date: dt.datetime | None = None
    patient: BenchPatientContext | None = None
    sample: BenchSampleContext
    analytes: list[str] = Field(default_factory=list)
    message: str
    guidance: BenchExamGuidance | None = None


class BenchTatItem(BaseModel):
    result_id: int
    exam_code: str
    target_minutes: int
    elapsed_minutes: float
    remaining_minutes: float
    due_at: dt.datetime
    patient: BenchPatientContext | None = None
    sample: BenchSampleContext
    guidance: BenchExamGuidance | None = None


class BenchRoutineItem(BaseModel):
    result_id: int
    exam_code: str | None = None
    analysis_date: dt.datetime | None = None
    patient: BenchPatientContext | None = None
    sample: BenchSampleContext
    analytes: list[str] = Field(default_factory=list)
    guidance: BenchExamGuidance | None = None


class BenchRadarResponse(BaseModel):
    generated_at: dt.datetime
    criticals: list[BenchCriticalItem] = Field(default_factory=list)
    tat_expiring: list[BenchTatItem] = Field(default_factory=list)
    routine: list[BenchRoutineItem] = Field(default_factory=list)
