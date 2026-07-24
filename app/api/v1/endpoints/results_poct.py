"""Saisie POCT (Point-of-Care Testing) — Flux 2, désactivée par défaut.

Les deux contrats historiques sont conservés pour compatibilité, mais aucune
saisie clinique n'est autorisée tant que le registre ``Equipment`` ne permet
pas d'identifier et de qualifier explicitement le profil Precix/ProCheck
Expert, ses analytes, unités et méthodes.

Le refus intervient avant tout calcul de plage, valeur critique, consommation
de réactif, audit de succès ou création de ``Result``.
"""

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Equipment, Patient, Sample, User
from app.schemas.poct import POCTBatchResponse, POCTBatchSubmission
from app.schemas.precis_expert import PrecisExpertManualInput
from app.services.patient_access import can_access_patient
from app.services.sample_workflow import (
    CancelledSampleError,
    ensure_sample_processable,
    lock_sample_by_barcode,
)

router = APIRouter(prefix="/results")


def _reject_unqualified_poct_equipment() -> NoReturn:
    """Bloque toute saisie tant qu'aucun profil d'équipement n'est qualifiable."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "poct_equipment_not_qualified",
            "message": (
                "Interface POCT désactivée : aucun profil Precix/ProCheck Expert "
                "n'est qualifié pour un usage clinique."
            ),
        },
    )


def _resolve_sample_and_patient(
    db: Session, *, barcode: str, current_user: User
) -> tuple[Sample, Patient]:
    """Résout l'échantillon et son patient, avec contrôle de périmètre."""
    sample = lock_sample_by_barcode(db, barcode)
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Erreur pre-analytique: code-barres {barcode} inconnu.",
        )
    patient = db.query(Patient).filter(Patient.id == sample.patient_id).first()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"L'echantillon {sample.barcode} n'est lie a aucun patient valide.",
        )
    if not can_access_patient(current_user, patient):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : dossier hors de votre périmètre.",
        )
    try:
        ensure_sample_processable(sample)
    except CancelledSampleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return sample, patient


@router.post("/precis-expert", status_code=status.HTTP_201_CREATED)
def submit_precis_expert_results(
    payload: PrecisExpertManualInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    _sample, _patient = _resolve_sample_and_patient(
        db, barcode=payload.sample_barcode, current_user=current_user
    )

    equipment = (
        db.query(Equipment)
        .filter(
            Equipment.serial_number == payload.equipment_serial,
            Equipment.name == "Precis Expert",
        )
        .first()
    )
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appareil POCT non enregistré ou non autorisé.",
        )

    _reject_unqualified_poct_equipment()


@router.post("/poct-batch", status_code=status.HTTP_201_CREATED, response_model=POCTBatchResponse)
def submit_poct_batch(
    payload: POCTBatchSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Refuse le lot tant que le profil POCT réel n'est pas qualifié."""
    _sample, _patient = _resolve_sample_and_patient(
        db, barcode=payload.sample_barcode, current_user=current_user
    )

    equipment = (
        db.query(Equipment)
        .filter(
            Equipment.serial_number == payload.device_serial,
            Equipment.name == payload.device_model,
        )
        .first()
    )
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appareil POCT non enregistré ou non autorisé.",
        )

    _reject_unqualified_poct_equipment()
