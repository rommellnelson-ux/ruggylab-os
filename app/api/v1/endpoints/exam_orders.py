"""API — Prescription d'examens (bon de demande) et suivi du fil.

Le médecin prescrit des examens ; la paillasse rattache l'échantillon prélevé
puis suit l'avancement par examen. La prescription est une AIDE : elle n'est
pas requise pour saisir un échantillon ou un résultat.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import ExamOrder, ExamOrderItem, Invoice, Patient, Result, Sample, User
from app.schemas.exam_order import (
    ORDER_STATUSES,
    PRIORITIES,
    ExamOrderCollect,
    ExamOrderCreate,
    ExamOrderRead,
    ExamOrderStatusUpdate,
    ExamOrderThread,
)
from app.schemas.invoice import InvoiceFromOrder, InvoiceRead
from app.services.accounting_service import balance_of, build_invoice_from_order, credit_of
from app.services.audit import log_audit_event
from app.services.exam_order_service import build_thread, sync_order_progress
from app.services.order_report import build_order_report_pdf
from app.services.patient_access import (
    apply_order_patient_scope,
    can_access_order,
    can_access_patient,
)

_OUT_OF_SCOPE = "Accès refusé : prescription hors de votre périmètre."

router = APIRouter(prefix="/exam-orders")


def _get_order_or_404(db: Session, order_id: int) -> ExamOrder:
    order = (
        db.query(ExamOrder)
        .options(selectinload(ExamOrder.items))
        .filter(ExamOrder.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prescription introuvable."
        )
    return order


def _get_accessible_order_or_404(db: Session, order_id: int, user: User) -> ExamOrder:
    """Charge la prescription en refusant (403) celles hors du périmètre unité."""
    order = _get_order_or_404(db, order_id)
    if not can_access_order(user, order):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUT_OF_SCOPE)
    return order


def _get_locked_accessible_order_or_404(db: Session, order_id: int, user: User) -> ExamOrder:
    """Verrouille la prescription avant tout contrôle de rattachement."""
    order = (
        db.query(ExamOrder)
        .options(selectinload(ExamOrder.items))
        .filter(ExamOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prescription introuvable."
        )
    if not can_access_order(user, order):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUT_OF_SCOPE)
    return order


@router.post("", response_model=ExamOrderRead, status_code=status.HTTP_201_CREATED)
def create_exam_order(
    payload: ExamOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExamOrder:
    if payload.priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Priorité invalide : {payload.priority}.")
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient introuvable.")
    if not can_access_patient(current_user, patient):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUT_OF_SCOPE)

    order = ExamOrder(
        patient_id=payload.patient_id,
        prescriber=payload.prescriber,
        requesting_service=payload.requesting_service,
        clinical_info=payload.clinical_info,
        priority=payload.priority,
        status="prescribed",
        created_by_id=current_user.id,
        items=[
            ExamOrderItem(exam_code=e.exam_code.strip().upper(), exam_label=e.exam_label)
            for e in payload.exams
        ],
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[ExamOrderRead])
def list_exam_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    patient_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ExamOrder]:
    query = db.query(ExamOrder).options(selectinload(ExamOrder.items))
    if status_filter:
        query = query.filter(ExamOrder.status == status_filter)
    if patient_id is not None:
        query = query.filter(ExamOrder.patient_id == patient_id)
    query = apply_order_patient_scope(query, current_user)  # cloisonnement par unité
    orders: list[ExamOrder] = query.order_by(ExamOrder.id.desc()).limit(limit).all()
    return orders


@router.get("/{order_id}", response_model=ExamOrderRead)
def get_exam_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExamOrder:
    return _get_accessible_order_or_404(db, order_id, current_user)


@router.get("/{order_id}/thread", response_model=ExamOrderThread)
def get_exam_order_thread(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExamOrderThread:
    """Le « fil » : avancement de chaque examen, de la prescription au résultat."""
    order = _get_accessible_order_or_404(db, order_id, current_user)
    return build_thread(db, order)


@router.post("/{order_id}/collect", response_model=ExamOrderThread)
def collect_exam_order(
    order_id: int,
    payload: ExamOrderCollect,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExamOrderThread:
    """Rattache l'échantillon prélevé (par id ou code-barres) et synchronise."""
    order = _get_locked_accessible_order_or_404(db, order_id, current_user)
    if payload.sample_id is None and not payload.barcode:
        raise HTTPException(status_code=422, detail="Fournir sample_id ou barcode.")

    sample = None
    if payload.sample_id is not None:
        sample = db.query(Sample).filter(Sample.id == payload.sample_id).first()
    elif payload.barcode:
        sample = db.query(Sample).filter(Sample.barcode == payload.barcode).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Échantillon introuvable.")

    if sample.patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Un échantillon sans patient ne peut pas être rattaché à cette prescription.",
        )
    if sample.patient_id != order.patient_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="L'échantillon et la prescription doivent appartenir au même patient.",
        )

    if order.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette prescription ne peut plus être collectée.",
        )
    if order.status == "completed":
        if order.sample_id == sample.id:
            return build_thread(db, order, synchronize=False)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette prescription ne peut plus être collectée.",
        )
    if order.sample_id is not None:
        if order.sample_id == sample.id:
            return build_thread(db, order, synchronize=False)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette prescription est déjà rattachée à un autre échantillon.",
        )
    order.sample_id = sample.id
    log_audit_event(
        db,
        user=current_user,
        event_type="exam_order.collect",
        entity_type="exam_order",
        entity_id=str(order.id),
        payload={"sample_id": sample.id, "patient_id": order.patient_id},
    )
    sync_order_progress(db, order)
    return build_thread(db, order, synchronize=False)


@router.patch("/{order_id}", response_model=ExamOrderRead)
def update_exam_order_status(
    order_id: int,
    payload: ExamOrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExamOrder:
    if payload.status not in ORDER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Statut invalide : {payload.status}.")
    order = _get_accessible_order_or_404(db, order_id, current_user)
    if payload.status == "cancelled":
        order.status = "cancelled"
        db.commit()
        db.refresh(order)
        return order
    # Pour les autres statuts, on laisse la dérivation automatique faire foi.
    order.status = payload.status
    db.commit()
    return sync_order_progress(db, order)


@router.post(
    "/{order_id}/invoice",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_invoice_from_order(
    order_id: int,
    payload: InvoiceFromOrder | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InvoiceRead:
    """Génère la facture des examens prescrits (tarifs catalogue + répartition CMU).

    Acte de facturation côté clinique (le comptable la gère ensuite). Refuse de
    créer un doublon si une facture active existe déjà pour cette prescription.
    """
    order = _get_accessible_order_or_404(db, order_id, current_user)
    existing = (
        db.query(Invoice)
        .filter(Invoice.exam_order_id == order_id, Invoice.status != "cancelled")
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Une facture existe déjà pour cette prescription ({existing.invoice_number}).",
        )
    options = payload or InvoiceFromOrder()
    if options.patient_type not in ("INSURED", "UNINSURED"):
        raise HTTPException(status_code=422, detail="patient_type invalide (INSURED/UNINSURED).")
    if options.patient_type == "INSURED" and not options.insurance_id:
        raise HTTPException(status_code=422, detail="Numéro CNAM obligatoire pour un assuré.")
    if not any(item.status != "cancelled" for item in order.items):
        raise HTTPException(
            status_code=422, detail="Aucun examen à facturer sur cette prescription."
        )

    invoice = build_invoice_from_order(db, order, options, created_by_id=current_user.id)
    read = InvoiceRead.model_validate(invoice)
    read.balance_xof = balance_of(invoice)
    read.credit_xof = credit_of(invoice)
    return read


@router.get("/{order_id}/report.pdf")
def order_report_pdf(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """Compte-rendu consolidé (PDF) regroupant tous les examens de la prescription."""
    order = _get_accessible_order_or_404(db, order_id, current_user)
    sync_order_progress(db, order)  # rafraîchit les liens examen -> résultat
    result_ids = [it.result_id for it in order.items if it.result_id]
    results = (
        {r.id: r for r in db.query(Result).filter(Result.id.in_(result_ids)).all()}
        if result_ids
        else {}
    )
    pdf_bytes = build_order_report_pdf(order, results)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="prescription-{order.id}.pdf"'},
    )
