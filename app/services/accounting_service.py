"""Service — comptabilité : calcul de facture, numérotation, encaissements.

Conforme CMU Côte d'Ivoire : pour un assuré, prise en charge CNAM 70 % et
ticket modérateur patient 30 % ; pour un non-assuré, reste à charge intégral.
Montants en FCFA (XOF), arrondis à l'entier (pas de centime de franc).
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ExamOrder, Invoice, InvoiceLine
from app.schemas.invoice import (
    FinanceSummary,
    InvoiceCreate,
    InvoiceFromOrder,
    InvoiceLineCreate,
)
from app.services.tariff_service import get_price

CNAM_RATE = Decimal("0.70")  # part assurance (assuré CMU)


def _xof(value: Decimal) -> Decimal:
    """Arrondit au franc CFA entier (le centime n'existe pas en XOF)."""
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def next_invoice_number(db: Session) -> str:
    """Numéro séquentiel lisible : FACT-AAAA-000001 (par année civile)."""
    year = dt.datetime.now(dt.UTC).year
    prefix = f"FACT-{year}-"
    count = (
        db.query(func.count(Invoice.id)).filter(Invoice.invoice_number.like(f"{prefix}%")).scalar()
        or 0
    )
    return f"{prefix}{count + 1:06d}"


def build_invoice(db: Session, payload: InvoiceCreate, *, created_by_id: int | None) -> Invoice:
    """Crée une facture : lignes, total brut, remise, répartition CMU."""
    gross = Decimal("0")
    lines: list[InvoiceLine] = []
    for line in payload.lines:
        line_total = _xof(Decimal(line.unit_price_xof) * line.quantity)
        gross += line_total
        lines.append(
            InvoiceLine(
                exam_code=line.exam_code,
                label=line.label,
                quantity=line.quantity,
                unit_price_xof=_xof(Decimal(line.unit_price_xof)),
                line_total_xof=line_total,
            )
        )

    discount = _xof(Decimal(payload.discount_xof))
    if discount > gross:
        discount = gross
    net = gross - discount

    if payload.patient_type == "INSURED":
        cnam = _xof(net * CNAM_RATE)
        patient_due = net - cnam
    else:
        cnam = Decimal("0")
        patient_due = net

    invoice = Invoice(
        invoice_number=next_invoice_number(db),
        patient_id=payload.patient_id,
        patient_label=payload.patient_label,
        exam_order_id=payload.exam_order_id,
        patient_type=payload.patient_type,
        insurance_id=payload.insurance_id,
        gross_total_xof=gross,
        discount_xof=discount,
        net_total_xof=net,
        cnam_part_xof=cnam,
        patient_due_xof=patient_due,
        paid_xof=Decimal("0"),
        status="issued",
        created_by_id=created_by_id,
        lines=lines,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def _patient_label(order: ExamOrder) -> str | None:
    """Libellé patient figé sur la facture (dénormalisé depuis la prescription)."""
    patient = order.patient  # FK non nullable : toujours présent
    last = (patient.last_name or "").upper()
    return f"{last} {patient.first_name or ''}".strip() or None


def build_invoice_from_order(
    db: Session, order: ExamOrder, options: InvoiceFromOrder, *, created_by_id: int | None
) -> Invoice:
    """Génère une facture à partir d'une prescription d'examens.

    Les lignes reprennent les examens demandés (hors annulés), au tarif courant
    du catalogue (0 si non tarifé). La répartition CMU et la numérotation
    réutilisent ``build_invoice``.
    """
    lines = [
        InvoiceLineCreate(
            exam_code=item.exam_code,
            label=item.exam_label or item.exam_code,
            quantity=1,
            unit_price_xof=get_price(db, item.exam_code) or Decimal("0"),
        )
        for item in order.items
        if item.status != "cancelled"
    ]
    payload = InvoiceCreate(
        patient_id=order.patient_id,
        patient_label=_patient_label(order),
        exam_order_id=order.id,
        patient_type=options.patient_type,
        insurance_id=options.insurance_id,
        lines=lines,
        discount_xof=options.discount_xof,
    )
    return build_invoice(db, payload, created_by_id=created_by_id)


def recompute_status(invoice: Invoice) -> None:
    """Met à jour le statut d'après le total encaissé (idempotent)."""
    if invoice.status == "cancelled":
        return
    paid = Decimal(invoice.paid_xof or 0)
    due = Decimal(invoice.patient_due_xof or 0)
    if paid <= 0:
        invoice.status = "issued"
    elif paid >= due:
        invoice.status = "paid"
    else:
        invoice.status = "partially_paid"


def balance_of(invoice: Invoice) -> Decimal:
    """Reste à payer par le patient (jamais négatif)."""
    bal = Decimal(invoice.patient_due_xof or 0) - Decimal(invoice.paid_xof or 0)
    return bal if bal > 0 else Decimal("0")


def finance_summary(db: Session) -> FinanceSummary:
    """Agrège le chiffre, l'encaissé et les créances (hors factures annulées)."""
    active = db.query(Invoice).filter(Invoice.status != "cancelled")
    rows = active.all()
    gross = sum((Decimal(i.gross_total_xof or 0) for i in rows), Decimal("0"))
    net = sum((Decimal(i.net_total_xof or 0) for i in rows), Decimal("0"))
    cnam = sum((Decimal(i.cnam_part_xof or 0) for i in rows), Decimal("0"))
    due = sum((Decimal(i.patient_due_xof or 0) for i in rows), Decimal("0"))
    collected = sum((Decimal(i.paid_xof or 0) for i in rows), Decimal("0"))
    outstanding = sum((balance_of(i) for i in rows), Decimal("0"))

    by_status: dict[str, int] = {}
    for inv in db.query(Invoice).all():
        by_status[inv.status] = by_status.get(inv.status, 0) + 1

    return FinanceSummary(
        invoice_count=len(rows),
        gross_total_xof=gross,
        net_total_xof=net,
        cnam_part_xof=cnam,
        patient_due_xof=due,
        collected_xof=collected,
        outstanding_xof=outstanding,
        by_status=by_status,
    )
