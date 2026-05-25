"""Schémas Pydantic pour le module BNPL (Buy Now Pay Later / micro-crédit santé CMU)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from pydantic import BaseModel, Field


class BNPLScheduleCreate(BaseModel):
    """Données nécessaires pour créer un plan de paiement fractionné."""

    patient_ref: Annotated[str, Field(min_length=1, max_length=200, description="Identifiant externe (insurance_id ou nom du patient)")]
    total_amount_xof: Annotated[int, Field(gt=0, description="Montant total en XOF")]
    installment_months: Annotated[int, Field(ge=2, le=24, description="Nombre de mensualités (minimum 2)")]
    prescriber_id: Annotated[str | None, Field(default=None, max_length=200, description="Identifiant du prescripteur")] = None


class BNPLPaymentOut(BaseModel):
    """Détail d'une échéance de paiement."""

    model_config = {"from_attributes": True}

    id: int
    installment_number: int
    due_date: dt.date
    paid_at: dt.datetime | None
    amount_xof: int
    status: str


class BNPLScheduleOut(BaseModel):
    """Détail complet d'un plan de paiement fractionné, avec toutes ses échéances."""

    model_config = {"from_attributes": True}

    id: int
    patient_ref: str
    total_amount_xof: int
    installment_months: int
    monthly_amount_xof: int
    created_at: dt.datetime
    status: str
    payments: list[BNPLPaymentOut] = []


class BNPLPaymentCreate(BaseModel):
    """Données pour enregistrer le paiement d'une échéance."""

    schedule_id: int
    installment_number: Annotated[int, Field(ge=1, description="Numéro de l'échéance (1..N)")]
    amount_xof: Annotated[int, Field(gt=0, description="Montant payé en XOF")]


class BNPLSummary(BaseModel):
    """Résumé financier d'un plan de paiement."""

    schedule_id: int
    patient_ref: str
    total_amount_xof: int
    paid_amount_xof: int
    remaining_xof: int
    overdue_count: int
    status: str
