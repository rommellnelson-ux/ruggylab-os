from pydantic import BaseModel, Field


class RuggylabJSONPoint(BaseModel):
    value: float
    unit: str
    status: str = Field(..., pattern=r"^[A-Z]{1,3}$")
    ref_range: str | None = None
    is_critical: bool = False


class CalibrationFlag(BaseModel):
    validated: bool = True
    equipment_serial: str | None = None


class HematologyDataDH36JSONB(BaseModel):
    WBC: RuggylabJSONPoint
    RBC: RuggylabJSONPoint
    HGB: RuggylabJSONPoint
    HCT: RuggylabJSONPoint
    MCV: RuggylabJSONPoint
    MCH: RuggylabJSONPoint
    MCHC: RuggylabJSONPoint
    PLT: RuggylabJSONPoint
    calibration: CalibrationFlag
    overall_flags: list[str] = Field(default_factory=list)
