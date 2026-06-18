import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.patient import PatientRead
from app.schemas.sample import SampleRead


class ResultBase(BaseModel):
    sample_id: int
    equipment_id: int | None = None
    analysis_date: dt.datetime | None = None
    data_points: dict = Field(default_factory=dict)
    image_url: str | None = None
    is_critical: bool = False


class ResultCreate(BaseModel):
    sample_id: int
    equipment_id: int | None = None
    analysis_date: dt.datetime | None = None
    data_points: dict = Field(default_factory=dict)
    image_url: str | None = None
    is_critical: bool = False
    exam_code: str | None = Field(default=None, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ResultRead(ResultBase):
    id: int
    validator_id: int | None = None
    is_validated: bool = False
    critical_ack_at: dt.datetime | None = None
    critical_ack_by_id: int | None = None
    delta_exceeded: bool = False
    delta_analytes: dict | None = None
    flags: dict | None = None
    is_auto_validated: bool = False
    auto_validated_at: dt.datetime | None = None
    amendment_reason: str | None = None
    # Suivi TAT
    exam_code: str | None = None
    registered_at: dt.datetime | None = None
    collected_at: dt.datetime | None = None
    received_at: dt.datetime | None = None
    analysis_finished_at: dt.datetime | None = None
    bio_validated_at: dt.datetime | None = None
    # Interprétation bioref complémentaire (unification des vocabulaires)
    bioref_status: str | None = None
    bioref_comment: str | None = None
    bioref_reference_range: str | None = None
    bioref_source: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ResultDetailRead(BaseModel):
    result: ResultRead
    sample: SampleRead | None = None
    patient: PatientRead | None = None
    bioref: dict | None = None


class ResultCockpitItem(BaseModel):
    result: ResultRead
    sample: SampleRead | None = None
    patient: PatientRead | None = None


class ResultHistoryItem(BaseModel):
    result: ResultRead
    sample: SampleRead | None = None
    shared_analytes: list[str] = Field(default_factory=list)
    delta_from_current: dict[str, float] = Field(default_factory=dict)


class ResultHistoryRead(BaseModel):
    result_id: int
    patient_id: int | None = None
    exam_code: str | None = None
    items: list[ResultHistoryItem] = Field(default_factory=list)


class ResultAmend(BaseModel):
    data_points: dict
    amendment_reason: str = Field(..., min_length=5, max_length=500)

    model_config = ConfigDict(extra="forbid")
