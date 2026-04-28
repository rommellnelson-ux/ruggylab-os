from pydantic import BaseModel, Field

from app.schemas.dh36_interfacing import RuggylabJSONPoint


class PrecisExpertManualInput(BaseModel):
    sample_barcode: str = Field(..., description="Code-barres de l'echantillon scanne")
    equipment_serial: str = Field(..., description="Numero de serie de l'appareil Precis Expert")
    glucose_raw: float
    glucose_unit: str = "g/L"
    cholesterol_raw: float
    cholesterol_unit: str = "g/L"
    uric_acid_raw: float
    uric_acid_unit: str = "mg/L"
    lactate_raw: float
    lactate_unit: str = "mmol/L"
    ketones_raw: float
    ketones_unit: str = "mmol/L"


class PrecisExpertJSONB(BaseModel):
    GLU: RuggylabJSONPoint
    CHOL: RuggylabJSONPoint
    UA: RuggylabJSONPoint
    LAC: RuggylabJSONPoint
    KET: RuggylabJSONPoint
    manual_entry_by: int
    entry_timestamp: str
