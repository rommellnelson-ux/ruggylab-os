from pydantic import BaseModel, ConfigDict, Field


class RegistreRowsRequest(BaseModel):
    rows: list[dict] = Field(..., min_length=1, max_length=10_000)
    model_config = ConfigDict(extra="forbid")


class RegistreImportRequest(BaseModel):
    rows: list[dict] = Field(..., min_length=1, max_length=10_000)
    dry_run: bool = Field(default=True, description="Si True, ne persiste rien.")
    confirm: bool = Field(default=False, description="Obligatoire pour un import réel.")
    model_config = ConfigDict(extra="forbid")
