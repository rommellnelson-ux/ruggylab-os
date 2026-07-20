"""Schémas POCT génériques (Point-of-Care Testing) — Flux 2.

Contrat **device-agnostique** pour la saisie manuelle groupée depuis le
« cockpit de saisie rapide » : un échantillon, N analytes mesurés, une seule
transaction. Le Precis Expert (glycémie, cholestérol, acide urique, lactate,
corps cétoniques) en est le premier cas d'usage ; un futur appareil POCT
réutilise le même contrat en déclarant ses analytes dans
``app.services.validation.poct_reference``.

Anti-faute de frappe : ``code`` est restreint au catalogue POCT connu.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.dh36_interfacing import RuggylabJSONPoint
from app.services.validation.poct_reference import POCT_ANALYTES, POCT_CODES


class POCTAnalyteInput(BaseModel):
    """Une mesure unitaire relevée sur l'appareil POCT."""

    code: str = Field(..., description=f"Code analyte POCT parmi {', '.join(POCT_CODES)}")
    value: float
    # Unité optionnelle : celle du catalogue est appliquée si absente.
    unit: str | None = Field(default=None, max_length=20)

    model_config = ConfigDict(extra="forbid")

    @field_validator("code")
    @classmethod
    def _known_code(cls, v: str) -> str:
        code = v.strip().upper()
        if code not in POCT_ANALYTES:
            raise ValueError(f"Code analyte POCT inconnu: {v!r}. Attendu: {', '.join(POCT_CODES)}.")
        return code


class POCTBatchSubmission(BaseModel):
    """Saisie groupée et simultanée de plusieurs analytes POCT."""

    sample_barcode: str = Field(..., min_length=1, max_length=100)
    device_serial: str = Field(..., min_length=1, max_length=100)
    device_model: str = Field(default="Precis Expert", max_length=100)
    measured_at: dt.datetime | None = None
    items: list[POCTAnalyteInput] = Field(..., min_length=1, max_length=len(POCT_CODES))

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _unique_codes(self) -> POCTBatchSubmission:
        codes = [item.code for item in self.items]
        duplicates = {c for c in codes if codes.count(c) > 1}
        if duplicates:
            raise ValueError(f"Analyte(s) en double dans le lot: {', '.join(sorted(duplicates))}.")
        return self


class POCTAnalyteResult(BaseModel):
    """Analyte validé, tel que renvoyé au cockpit après enregistrement."""

    code: str
    label: str
    point: RuggylabJSONPoint


class POCTBatchResponse(BaseModel):
    status: str
    message: str
    result_id: int
    is_critical: bool
    analytes: list[POCTAnalyteResult] = Field(default_factory=list)
