"""Schémas — Comptabilité : facturation des examens (FCFA), CMU, encaissements."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

PATIENT_TYPES = ("INSURED", "UNINSURED")
PAYMENT_METHODS = ("CASH", "MOBILE_MONEY", "INSURANCE", "BNPL")
INVOICE_STATUSES = ("draft", "issued", "partially_paid", "paid", "cancelled")


class InvoiceLineCreate(BaseModel):
    exam_code: str | None = Field(default=None, max_length=50)
    label: str = Field(..., min_length=1, max_length=150)
    quantity: int = Field(default=1, ge=1, le=999)
    unit_price_xof: Decimal = Field(..., ge=0)
    model_config = ConfigDict(extra="forbid")


class InvoiceCreate(BaseModel):
    patient_id: int | None = None
    patient_label: str | None = Field(default=None, max_length=150)
    exam_order_id: int | None = None
    patient_type: str = Field(default="UNINSURED")
    insurance_id: str | None = Field(default=None, max_length=50)
    lines: list[InvoiceLineCreate] = Field(..., min_length=1)
    discount_xof: Decimal = Field(default=Decimal("0"), ge=0)
    model_config = ConfigDict(extra="forbid")


class PaymentCreate(BaseModel):
    amount_xof: Decimal = Field(..., gt=0)
    method: str = Field(default="CASH")
    reference: str | None = Field(default=None, max_length=100)
    model_config = ConfigDict(extra="forbid")


class InvoiceLineRead(BaseModel):
    id: int
    exam_code: str | None = None
    label: str
    quantity: int
    unit_price_xof: Decimal
    line_total_xof: Decimal
    model_config = ConfigDict(from_attributes=True)


class PaymentRead(BaseModel):
    id: int
    amount_xof: Decimal
    method: str
    reference: str | None = None
    paid_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)


class InvoiceRead(BaseModel):
    id: int
    invoice_number: str
    patient_id: int | None = None
    patient_label: str | None = None
    exam_order_id: int | None = None
    patient_type: str
    insurance_id: str | None = None
    gross_total_xof: Decimal
    discount_xof: Decimal
    net_total_xof: Decimal
    cnam_part_xof: Decimal
    patient_due_xof: Decimal
    paid_xof: Decimal
    balance_xof: Decimal = Decimal("0")
    status: str
    issued_at: dt.datetime
    lines: list[InvoiceLineRead] = Field(default_factory=list)
    payments: list[PaymentRead] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class FinanceSummary(BaseModel):
    """Tableau de bord comptable : chiffre, encaissé, créances."""

    invoice_count: int
    gross_total_xof: Decimal
    net_total_xof: Decimal
    cnam_part_xof: Decimal
    patient_due_xof: Decimal
    collected_xof: Decimal
    outstanding_xof: Decimal
    by_status: dict[str, int] = Field(default_factory=dict)
