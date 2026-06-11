from pydantic import BaseModel, ConfigDict, Field


class BioRefRangeRead(BaseModel):
    id: int
    test_code: str
    test_name: str
    category: str | None = None
    specimen: str | None = None
    sex: str = "ALL"
    age_min_years: float = 0
    age_max_years: float = 120
    lower_limit: float | None = None
    upper_limit: float | None = None
    unit: str | None = None
    normal_text: str | None = None
    critical_low: float | None = None
    critical_high: float | None = None
    interpretation: str | None = None
    source: str | None = None
    is_active: bool = True
    model_config = ConfigDict(from_attributes=True)


class BioRefInterpretRequest(BaseModel):
    test_code: str = Field(..., min_length=1, max_length=50)
    value: float | None = Field(default=None, description="Valeur numérique ; None pour un test qualitatif")
    sex: str | None = None
    age_years: float | None = Field(default=None, ge=0, le=130)
    model_config = ConfigDict(extra="forbid")
