from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MilitaryFacilityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., min_length=1, max_length=10)  # HMA, CMA, CSA
    division: str = Field(..., min_length=1, max_length=50)  # ARMEES, GENDARMERIE NATIONALE, HMA
    region: str = Field(..., min_length=1, max_length=50)
    bureau: str = Field(..., min_length=1, max_length=100)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

    @model_validator(mode="after")
    def validate_type_division(self) -> Self:
        valid_types = {"HMA", "CMA", "CSA"}
        valid_divisions = {"ARMEES", "GENDARMERIE NATIONALE", "HMA"}

        if self.type not in valid_types:
            raise ValueError(f"type must be one of {valid_types}")
        if self.division not in valid_divisions:
            raise ValueError(f"division must be one of {valid_divisions}")
        return self


class MilitaryFacilityCreate(MilitaryFacilityBase):
    model_config = ConfigDict(extra="forbid")


class MilitaryFacilityRead(MilitaryFacilityBase):
    id: int

    model_config = ConfigDict(from_attributes=True)