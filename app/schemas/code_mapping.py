import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class CodeMappingCreate(BaseModel):
    canonical_code: str = Field(..., min_length=1, max_length=50)
    exam_code: str | None = Field(default=None, max_length=50)
    test_code: str | None = Field(default=None, max_length=50)
    analyte_code: str | None = Field(default=None, max_length=50)
    component_of: str | None = Field(default=None, max_length=50)
    label: str | None = Field(default=None, max_length=150)
    category: str | None = Field(default=None, max_length=100)
    specimen_type: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=50)
    is_panel: bool = False
    priority: int = Field(default=100, ge=0, le=10_000)
    model_config = ConfigDict(extra="forbid")


class CodeMappingRead(CodeMappingCreate):
    id: int
    is_active: bool = True
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)


class CodeMappingTestRequest(BaseModel):
    exam_code: str | None = None
    analyte_code: str | None = None
    sex: str | None = None
    model_config = ConfigDict(extra="forbid")
