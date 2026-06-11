"""API — Unification des vocabulaires biologiques (table de correspondance)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import BiologicalCodeMapping, User
from app.schemas.code_mapping import (
    CodeMappingCreate,
    CodeMappingRead,
    CodeMappingTestRequest,
)
from app.services.code_mapping_service import (
    find_orphans,
    get_bioref_code_for_result,
    get_canonical_code,
    list_active,
    resolve_from_exam_code,
    seed_mappings,
)

router = APIRouter(prefix="/code-mappings")


@router.get("", response_model=list[CodeMappingRead])
def list_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[BiologicalCodeMapping]:
    """Liste les correspondances actives (panels et composants)."""
    del current_user
    return list_active(db)


@router.get("/orphans")
def list_orphan_codes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Codes de catalogue/bioref sans correspondance."""
    del current_user
    return find_orphans(db)


@router.post("/seed-defaults")
def seed_defaults(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, int]:
    """Charge les correspondances prioritaires (idempotent)."""
    del current_user
    return {"created": seed_mappings(db)}


@router.post("/test")
def test_mapping(
    payload: CodeMappingTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Teste la résolution d'un (exam_code[, analyte_code]) vers le bioref."""
    del current_user
    mapping = resolve_from_exam_code(db, payload.exam_code)
    return {
        "exam_code": payload.exam_code,
        "analyte_code": payload.analyte_code,
        "canonical_code": get_canonical_code(
            db, exam_code=payload.exam_code, analyte_code=payload.analyte_code
        ),
        "is_panel": mapping.is_panel if mapping else False,
        "bioref_test_code": get_bioref_code_for_result(
            db, payload.exam_code, payload.analyte_code, payload.sex
        ),
        "matched": mapping is not None,
    }


@router.post("", response_model=CodeMappingRead, status_code=status.HTTP_201_CREATED)
def create_mapping(
    payload: CodeMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> BiologicalCodeMapping:
    """Crée une correspondance (réservé officier/admin)."""
    del current_user
    mapping = BiologicalCodeMapping(**payload.model_dump())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


@router.delete("/{mapping_id}", status_code=status.HTTP_200_OK)
def deactivate_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    """Désactive une correspondance (suppression logique)."""
    del current_user
    mapping = db.query(BiologicalCodeMapping).filter(BiologicalCodeMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Correspondance introuvable."
        )
    mapping.is_active = False
    db.commit()
    return {"status": "deactivated"}
