"""Schémas — Prescription d'examens (bon de demande d'analyses) et suivi du fil."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

# Statuts du bon de prescription et de chaque examen demandé.
ORDER_STATUSES = ("prescribed", "collected", "in_progress", "completed", "cancelled")
ITEM_STATUSES = ("pending", "resulted", "cancelled")
PRIORITIES = ("routine", "urgent", "stat")


class ExamOrderItemCreate(BaseModel):
    exam_code: str = Field(..., min_length=1, max_length=50)
    exam_label: str | None = Field(default=None, max_length=150)
    model_config = ConfigDict(extra="forbid")


class ExamOrderCreate(BaseModel):
    patient_id: int
    prescriber: str | None = Field(default=None, max_length=150)
    requesting_service: str | None = Field(default=None, max_length=100)
    clinical_info: str | None = None
    priority: str = Field(default="routine")
    exams: list[ExamOrderItemCreate] = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")


class ExamOrderStatusUpdate(BaseModel):
    status: str
    model_config = ConfigDict(extra="forbid")


class ExamOrderCollect(BaseModel):
    """Rattache l'échantillon prélevé au bon (par id ou code-barres)."""

    sample_id: int | None = None
    barcode: str | None = None
    model_config = ConfigDict(extra="forbid")


class ExamOrderItemRead(BaseModel):
    id: int
    exam_code: str
    exam_label: str | None = None
    status: str
    result_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class ExamOrderRead(BaseModel):
    id: int
    patient_id: int
    prescriber: str | None = None
    requesting_service: str | None = None
    clinical_info: str | None = None
    priority: str
    status: str
    ordered_at: dt.datetime
    sample_id: int | None = None
    items: list[ExamOrderItemRead] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class ExamThreadStep(BaseModel):
    """Une étape du fil pour un examen demandé."""

    exam_code: str
    exam_label: str | None = None
    status: str  # pending | resulted | cancelled
    result_id: int | None = None
    is_critical: bool = False
    is_validated: bool = False
    preanalytics: dict | None = None
    technical_sheet: dict | None = None


class ExamOrderThread(BaseModel):
    """Vue « fil » du bon : où en est chaque examen, de bout en bout."""

    order_id: int
    status: str
    priority: str
    patient_id: int
    patient_label: str | None = None
    prescriber: str | None = None
    ordered_at: dt.datetime
    sample_id: int | None = None
    sample_barcode: str | None = None
    sample_status: str | None = None
    total_exams: int
    resulted_exams: int
    progress_pct: int
    steps: list[ExamThreadStep] = Field(default_factory=list)
