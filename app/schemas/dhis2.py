import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_uid(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{10}", value):
        raise ValueError("UID DHIS2 invalide.")
    return value


class Dhis2MappingCreate(BaseModel):
    internal_code: str = Field(min_length=2, max_length=50)
    data_element_uid: str
    data_set_uid: str
    org_unit_uid: str
    category_option_combo_uid: str | None = None
    period_type: str = "monthly"
    active: bool = True
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None

    @field_validator(
        "data_element_uid",
        "data_set_uid",
        "org_unit_uid",
        "category_option_combo_uid",
    )
    @classmethod
    def validate_uid(cls, value: str | None) -> str | None:
        return _validate_uid(value) if value is not None else None

    @field_validator("internal_code")
    @classmethod
    def normalize_internal_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("period_type")
    @classmethod
    def validate_period_type(cls, value: str) -> str:
        if value != "monthly":
            raise ValueError("Seule la périodicité mensuelle est activée dans le pilote.")
        return value


class Dhis2MappingRead(Dhis2MappingCreate):
    id: int
    created_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)


class Dhis2IndicatorValue(BaseModel):
    code: str
    label: str
    value: int
    data_element_uid: str
    category_option_combo_uid: str | None = None


class Dhis2PreviewRead(BaseModel):
    period: str
    data_set_uid: str
    org_unit_uid: str
    complete_date: dt.date
    indicators: list[Dhis2IndicatorValue]
    warnings: list[str] = []
    payload: dict


class Dhis2ExportCreate(BaseModel):
    period: str = Field(pattern=r"^\d{6}$")
    data_set_uid: str
    org_unit_uid: str

    @field_validator("data_set_uid", "org_unit_uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        return _validate_uid(value)


class Dhis2ExportRead(BaseModel):
    id: int
    period: str
    data_set_uid: str
    org_unit_uid: str
    status: str
    payload: dict
    payload_sha256: str
    created_by_user_id: int | None
    validated_by_user_id: int | None
    created_at: dt.datetime
    validated_at: dt.datetime | None
    error_message: str | None
    model_config = ConfigDict(from_attributes=True)
