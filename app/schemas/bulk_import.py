from pydantic import BaseModel, ConfigDict, Field


class BulkImportRequest(BaseModel):
    csv: str = Field(..., min_length=1, max_length=2_000_000, description="Contenu CSV brut")
    dry_run: bool = Field(default=False, description="Valide sans persister si True")
    model_config = ConfigDict(extra="forbid")


class BulkImportError(BaseModel):
    row: int
    error: str


class BulkImportResult(BaseModel):
    total: int
    created: int
    errors: list[BulkImportError]
    dry_run: bool = False
