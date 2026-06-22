"""API — Comptabilité : facturation des examens, encaissements, créances.

Cloisonné via ``require_finance`` : comptable et administrateur uniquement.
Les libellés patient sont figés sur la facture (le comptable n'accède pas aux
dossiers cliniques).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_finance
from app.db.session import get_db
from app.models import Invoice, InvoicePayment, User
from app.schemas.bnpl import BNPLScheduleCreate, BNPLScheduleOut
from app.schemas.invoice import (
    INVOICE_STATUSES,
    PAYMENT_METHODS,
    FinanceSummary,
    InvoiceCreate,
    InvoiceRead,
    PaymentCreate,
    PaymentPlanCreate,
)
from app.services.accounting_service import (
    balance_of,
    build_invoice,
    finance_summary,
    recompute_status,
)
from app.services.bnpl_tracker import BNPLTracker
from app.services.invoice_pdf import build_invoice_receipt_pdf

_bnpl = BNPLTracker()

router = APIRouter(prefix="/invoices")


def _to_read(invoice: Invoice) -> InvoiceRead:
    read = InvoiceRead.model_validate(invoice)
    read.balance_xof = balance_of(invoice)
    return read


def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.lines), selectinload(Invoice.payments))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable.")
    return invoice


@router.post("", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> InvoiceRead:
    if payload.patient_type not in ("INSURED", "UNINSURED"):
        raise HTTPException(status_code=422, detail="patient_type invalide (INSURED/UNINSURED).")
    if payload.patient_type == "INSURED" and not payload.insurance_id:
        raise HTTPException(status_code=422, detail="Numéro CNAM obligatoire pour un assuré.")
    invoice = build_invoice(db, payload, created_by_id=current_user.id)
    return _to_read(invoice)


@router.get("/summary", response_model=FinanceSummary)
def get_finance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> FinanceSummary:
    del current_user
    return finance_summary(db)


@router.get("", response_model=list[InvoiceRead])
def list_invoices(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> list[InvoiceRead]:
    del current_user
    query = db.query(Invoice).options(selectinload(Invoice.lines), selectinload(Invoice.payments))
    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    invoices = query.order_by(Invoice.id.desc()).limit(limit).all()
    return [_to_read(inv) for inv in invoices]


@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> InvoiceRead:
    del current_user
    return _to_read(_get_invoice_or_404(db, invoice_id))


@router.post("/{invoice_id}/payments", response_model=InvoiceRead)
def record_payment(
    invoice_id: int,
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> InvoiceRead:
    if payload.method not in PAYMENT_METHODS:
        raise HTTPException(
            status_code=422, detail=f"Mode de paiement invalide : {payload.method}."
        )
    invoice = _get_invoice_or_404(db, invoice_id)
    if invoice.status == "cancelled":
        raise HTTPException(status_code=409, detail="Facture annulée : encaissement impossible.")

    invoice.payments.append(
        InvoicePayment(
            amount_xof=payload.amount_xof,
            method=payload.method,
            reference=payload.reference,
            received_by_id=current_user.id,
        )
    )
    invoice.paid_xof = Decimal(invoice.paid_xof or 0) + Decimal(payload.amount_xof)
    recompute_status(invoice)
    db.commit()
    db.refresh(invoice)
    return _to_read(invoice)


@router.post("/{invoice_id}/cancel", response_model=InvoiceRead)
def cancel_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> InvoiceRead:
    del current_user
    invoice = _get_invoice_or_404(db, invoice_id)
    if Decimal(invoice.paid_xof or 0) > 0:
        raise HTTPException(
            status_code=409, detail="Facture déjà encaissée : annulation impossible."
        )
    invoice.status = "cancelled"
    db.commit()
    db.refresh(invoice)
    return _to_read(invoice)


@router.get("/{invoice_id}/receipt.pdf")
def invoice_receipt_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> Response:
    """Reçu/facture PDF (FCFA) imprimable pour le patient."""
    del current_user
    invoice = _get_invoice_or_404(db, invoice_id)
    pdf_bytes = build_invoice_receipt_pdf(invoice)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.invoice_number}.pdf"'},
    )


@router.post("/{invoice_id}/payment-plan", response_model=BNPLScheduleOut)
def create_payment_plan(
    invoice_id: int,
    payload: PaymentPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> BNPLScheduleOut:
    """Échelonne le reste à charge en plan BNPL (optionnel).

    À n'utiliser que lorsque le patient ne peut pas régler comptant : crée un
    plan de paiement fractionné sur le solde et le rattache à la facture.
    """
    del current_user
    invoice = _get_invoice_or_404(db, invoice_id)
    if invoice.status == "cancelled":
        raise HTTPException(status_code=409, detail="Facture annulée : plan impossible.")
    if invoice.payment_plan_id:
        raise HTTPException(
            status_code=409, detail="Un plan de paiement existe déjà pour cette facture."
        )
    balance = balance_of(invoice)
    if balance <= 0:
        raise HTTPException(status_code=409, detail="Aucun reste à charge à échelonner.")

    schedule = _bnpl.create_schedule(
        db,
        BNPLScheduleCreate(
            patient_ref=invoice.patient_label or invoice.invoice_number,
            total_amount_xof=int(balance),
            installment_months=payload.installment_months,
        ),
    )
    invoice.payment_plan_id = schedule.id
    db.commit()
    return schedule


# Réservé : statuts exposés pour cohérence d'API/documentation.
_ = INVOICE_STATUSES
