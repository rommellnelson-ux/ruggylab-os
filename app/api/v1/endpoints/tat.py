"""API — Suivi du TAT (Turnaround Time) : cibles, saisie, tableau de bord, alertes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import Result, TatTarget, User
from app.schemas.tat import ResultTatUpdate, TatTargetCreate, TatTargetRead
from app.services.audit import log_audit_event
from app.services.tat_service import (
    compute_result_tat,
    compute_tat_dashboard,
    list_tat_alerts,
    seed_default_targets,
)

router = APIRouter(prefix="/tat")


# ── Catalogue d'examens (référentiel, dérivé du registre réel) ──────────────


@router.get("/catalog")
def exam_catalog(
    current_user: User = Depends(get_current_active_user),
) -> list[dict]:
    """Catalogue de référence des examens, enrichi des consignes terrain."""
    del current_user
    from app.services.exam_catalog import EXAM_CATALOG

    return EXAM_CATALOG


@router.get("/catalog-audit")
def exam_catalog_audit(
    current_user: User = Depends(require_officer),
) -> dict:
    """État de complétude et de validation locale des fiches du catalogue."""
    del current_user
    from app.services.exam_catalog import audit_exam_catalog

    return audit_exam_catalog()


@router.get("/catalog/{exam_code}")
def exam_catalog_detail(
    exam_code: str,
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Détail d'un examen : TAT, pré-analytique et fiche technique paillasse."""
    del current_user
    from app.services.exam_catalog import exam_catalog_entry

    entry = exam_catalog_entry(exam_code)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Examen inconnu : {exam_code}.",
        )
    return entry


# ── Cibles TAT par examen ───────────────────────────────────────────────────


@router.get("/targets", response_model=list[TatTargetRead])
def list_targets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[TatTarget]:
    del current_user
    return (
        db.query(TatTarget)
        .filter(TatTarget.is_active.is_(True))
        .order_by(TatTarget.exam_code)
        .all()
    )


@router.post("/targets", response_model=TatTargetRead, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: TatTargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> TatTarget:
    existing = db.query(TatTarget).filter(TatTarget.exam_code == payload.exam_code).first()
    if existing and existing.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cible TAT déjà définie pour l'examen {payload.exam_code}.",
        )
    if existing:  # réactive + met à jour une cible précédemment désactivée
        existing.label = payload.label
        existing.target_minutes = payload.target_minutes
        existing.warn_factor = payload.warn_factor
        existing.is_active = True
        target = existing
    else:
        target = TatTarget(**payload.model_dump())
        db.add(target)
    db.commit()
    db.refresh(target)
    return target


@router.delete("/targets/{target_id}", status_code=status.HTTP_200_OK)
def deactivate_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    del current_user
    target = db.query(TatTarget).filter(TatTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cible TAT introuvable.")
    target.is_active = False
    db.commit()
    return {"status": "deactivated"}


@router.post("/targets/seed-defaults")
def seed_defaults(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, int]:
    """Crée les délais cibles standards manquants (NFS, Glycémie, Créatinine, GE, ECBU)."""
    del current_user
    created = seed_default_targets(db)
    return {"created": created}


# ── Saisie / consultation TAT d'un résultat ────────────────────────────────


@router.get("/results/{result_id}")
def get_result_tat(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    del current_user
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Résultat introuvable.")
    target = None
    if result.exam_code:
        target = (
            db.query(TatTarget)
            .filter(TatTarget.exam_code == result.exam_code, TatTarget.is_active.is_(True))
            .first()
        )
    return compute_result_tat(result, target)


@router.patch("/results/{result_id}")
def update_result_tat(
    result_id: int,
    payload: ResultTatUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Met à jour les horodatages TAT d'un résultat (saisie manuelle des phases)."""
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Résultat introuvable.")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Aucun champ à mettre à jour."
        )
    for key, value in changes.items():
        setattr(result, key, value)
    log_audit_event(
        db,
        user=current_user,
        event_type="tat.result.update",
        entity_type="result",
        entity_id=str(result_id),
        payload={"fields": sorted(changes.keys())},
    )
    db.commit()
    db.refresh(result)
    target = None
    if result.exam_code:
        target = (
            db.query(TatTarget)
            .filter(TatTarget.exam_code == result.exam_code, TatTarget.is_active.is_(True))
            .first()
        )
    return compute_result_tat(result, target)


# ── Tableau de bord & alertes ───────────────────────────────────────────────


@router.get("/dashboard")
def tat_dashboard(
    days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Indicateurs de performance TAT : par examen, technicien, automate, jour."""
    del current_user
    return compute_tat_dashboard(db, days=days)


@router.get("/alerts")
def tat_alerts(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[dict]:
    """Résultats récents ayant dépassé leur délai cible (retard modéré ou important)."""
    del current_user
    return list_tat_alerts(db, days=days)
