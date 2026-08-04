from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.api.deps import get_current_active_user, require_admin, require_officer
from app.db.session import get_db
from app.models import (
    Equipment,
    EquipmentDocument,
    EquipmentInterface,
    EquipmentQualification,
    User,
    UserRole,
)
from app.schemas.equipment import (
    EquipmentActionReason,
    EquipmentApprovedAnalyteCreate,
    EquipmentApprovedAnalyteRead,
    EquipmentApprovedAnalyteUpdate,
    EquipmentCreate,
    EquipmentDetailRead,
    EquipmentDocumentCreate,
    EquipmentDocumentRead,
    EquipmentDocumentUpdate,
    EquipmentIdentityUpdate,
    EquipmentInterfaceCreate,
    EquipmentInterfaceDirection,
    EquipmentInterfaceRead,
    EquipmentInterfaceType,
    EquipmentInterfaceUpdate,
    EquipmentQualificationDraftCreate,
    EquipmentQualificationDraftUpdate,
    EquipmentQualificationNewVersion,
    EquipmentQualificationRead,
    EquipmentQualificationTechnicalTransition,
    EquipmentReadinessRead,
    EquipmentReadinessStatus,
    EquipmentSimpleRead,
)
from app.services.equipment_registry import (
    EquipmentReadinessAssessment,
    EquipmentRegistryError,
    add_approved_analyte,
    approve_qualification,
    assess_interface_readiness,
    create_equipment,
    create_interface,
    create_new_qualification_version,
    create_qualification_draft,
    disable_interface,
    enable_interface,
    mask_registered_reference,
    mask_serial_number,
    register_document,
    submit_qualification,
    suspend_qualification,
    transition_qualification_technical_status,
    update_approved_analyte,
    update_document,
    update_equipment_identity,
    update_interface,
    update_qualification_draft,
)

router = APIRouter(prefix="/equipments")


def _equipment_or_404(db: Session, equipment_id: int) -> Equipment:
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if equipment is None:
        raise HTTPException(status_code=404, detail="Equipement introuvable.")
    return equipment


@contextmanager
def _registry_transaction(db: Session) -> Generator[None, None, None]:
    try:
        yield
        db.commit()
    except EquipmentRegistryError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except Exception:
        db.rollback()
        raise


def _detail(equipment: Equipment) -> EquipmentDetailRead:
    return EquipmentDetailRead(
        id=equipment.id,
        name=equipment.name,
        serial_number_masked=mask_serial_number(equipment.serial_number),
        type=equipment.type,
        location=equipment.location,
        last_calibration=equipment.last_calibration,
        manufacturer=equipment.manufacturer,
        model=equipment.model,
        device_family=equipment.device_family,
        firmware_version=equipment.firmware_version,
        unit=equipment.unit,
        clinical_use=equipment.clinical_use,
        lifecycle_status=equipment.lifecycle_status,
        asset_identifier=equipment.asset_identifier,
        updated_at=equipment.updated_at,
    )


def _interface_read(interface: EquipmentInterface) -> EquipmentInterfaceRead:
    return EquipmentInterfaceRead(
        id=interface.id,
        equipment_id=interface.equipment_id,
        stable_identifier=interface.stable_identifier,
        interface_type=EquipmentInterfaceType(interface.interface_type),
        direction=EquipmentInterfaceDirection(interface.direction),
        endpoint_reference_masked=mask_registered_reference(interface.endpoint_reference),
        protocol_name=interface.protocol_name,
        protocol_version=interface.protocol_version,
        driver_name=interface.driver_name,
        driver_version=interface.driver_version,
        configuration_version=interface.configuration_version,
        enabled=interface.enabled,
        archived=interface.archived,
        created_at=interface.created_at,
        updated_at=interface.updated_at,
        disabled_at=interface.disabled_at,
        disable_reason=interface.disable_reason,
    )


def _document_read(document: EquipmentDocument) -> EquipmentDocumentRead:
    return EquipmentDocumentRead(
        id=document.id,
        equipment_id=document.equipment_id,
        document_title=document.document_title,
        document_type=document.document_type,
        manufacturer=document.manufacturer,
        model=document.model,
        version=document.version,
        language=document.language,
        document_date=document.document_date,
        page_count=document.page_count,
        physical_copy_available=document.physical_copy_available,
        digital_copy_available=document.digital_copy_available,
        storage_reference_masked=mask_registered_reference(document.storage_reference),
        contains_connectivity_section=document.contains_connectivity_section,
        contains_protocol_specification=document.contains_protocol_specification,
        review_status=document.review_status,
        review_date=document.review_date,
        checksum_present=bool(document.checksum),
        archived_at=document.archived_at,
        created_at=document.created_at,
    )


def _readiness_read(
    assessment: EquipmentReadinessAssessment,
) -> EquipmentReadinessRead:
    return EquipmentReadinessRead(
        equipment_id=assessment.equipment_id,
        interface_id=assessment.interface_id,
        activatable=assessment.activatable,
        enabled=assessment.enabled,
        readiness_status=assessment.readiness_status,
        satisfied_conditions=list(assessment.satisfied_conditions),
        missing_conditions=list(assessment.missing_conditions),
        active_qualification_id=assessment.active_qualification_id,
        active_qualification_version=assessment.active_qualification_version,
        qualification_expires_at=assessment.qualification_expires_at,
        configuration_version=assessment.configuration_version,
        driver_name=assessment.driver_name,
        driver_version=assessment.driver_version,
        protocol_name=assessment.protocol_name,
        protocol_version=assessment.protocol_version,
    )


def _simple_status(db: Session, equipment: Equipment) -> tuple[EquipmentReadinessStatus, list[str]]:
    assessments = [
        assess_interface_readiness(db, interface)
        for interface in equipment.interfaces
        if not interface.archived
    ]
    if not assessments:
        missing = ["identity", "interface", "qualification"]
        if not equipment.manufacturer or not equipment.model or not equipment.device_family:
            missing.insert(0, "technical_identity")
        return EquipmentReadinessStatus.UNQUALIFIED, sorted(set(missing))

    statuses = {item.readiness_status for item in assessments}
    precedence = (
        EquipmentReadinessStatus.ENABLED,
        EquipmentReadinessStatus.SUSPENDED,
        EquipmentReadinessStatus.QUALIFIED_DISABLED,
        EquipmentReadinessStatus.CLINICAL_APPROVAL_REQUIRED,
        EquipmentReadinessStatus.TECHNICAL_TESTING,
        EquipmentReadinessStatus.DOCUMENTATION_MISSING,
        EquipmentReadinessStatus.UNQUALIFIED,
    )
    selected = next(item for item in precedence if item in statuses)
    missing_codes = {code for assessment in assessments for code in assessment.missing_conditions}
    categories: set[str] = set()
    for code in missing_codes:
        if code.startswith("equipment_") or code.startswith(("manufacturer", "model", "device_")):
            categories.add("technical_identity")
        elif code.startswith(("interface", "protocol", "driver", "configuration", "firmware")):
            categories.add("interface_configuration")
        elif code.startswith(("evidence", "document")):
            categories.add("documentation")
        elif code.startswith(("approved_analyte",)):
            categories.add("clinical_scope")
        else:
            categories.add("qualification")
    return selected, sorted(categories)


def _equipment_query_for_simple_view(db: Session, user: User) -> Query[Equipment]:
    query = db.query(Equipment)
    if user.role not in {UserRole.ADMIN, UserRole.OFFICER} and user.unit is not None:
        query = query.filter(or_(Equipment.unit == user.unit, Equipment.unit.is_(None)))
    return query


@router.get("", response_model=list[EquipmentSimpleRead])
def list_equipments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[EquipmentSimpleRead]:
    if current_user.role == UserRole.ACCOUNTANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vue equipement non necessaire au profil comptable.",
        )
    items: list[EquipmentSimpleRead] = []
    for equipment in _equipment_query_for_simple_view(db, current_user).order_by(
        Equipment.id.desc()
    ):
        readiness_status, categories = _simple_status(db, equipment)
        items.append(
            EquipmentSimpleRead(
                id=equipment.id,
                name=equipment.name,
                type=equipment.type,
                device_family=equipment.device_family,
                location=equipment.location,
                unit=equipment.unit,
                lifecycle_status=equipment.lifecycle_status,
                clinical_use=equipment.clinical_use,
                readiness_status=readiness_status,
                missing_condition_categories=categories,
            )
        )
    return items


@router.post(
    "",
    response_model=EquipmentDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_equipment_endpoint(
    payload: EquipmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentDetailRead:
    with _registry_transaction(db):
        equipment = create_equipment(db, payload=payload, user=current_user)
    db.refresh(equipment)
    return _detail(equipment)


@router.get("/{equipment_id}/details", response_model=EquipmentDetailRead)
def get_equipment_details(
    equipment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_officer),
) -> EquipmentDetailRead:
    return _detail(_equipment_or_404(db, equipment_id))


@router.patch("/{equipment_id}", response_model=EquipmentDetailRead)
def patch_equipment_identity(
    equipment_id: int,
    payload: EquipmentIdentityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentDetailRead:
    with _registry_transaction(db):
        equipment = update_equipment_identity(
            db,
            equipment_id=equipment_id,
            payload=payload,
            user=current_user,
        )
    db.refresh(equipment)
    return _detail(equipment)


@router.get("/{equipment_id}/interfaces", response_model=list[EquipmentInterfaceRead])
def list_interfaces(
    equipment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_officer),
) -> list[EquipmentInterfaceRead]:
    _equipment_or_404(db, equipment_id)
    interfaces = (
        db.query(EquipmentInterface)
        .filter(EquipmentInterface.equipment_id == equipment_id)
        .order_by(EquipmentInterface.id)
        .all()
    )
    return [_interface_read(interface) for interface in interfaces]


@router.post(
    "/{equipment_id}/interfaces",
    response_model=EquipmentInterfaceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_equipment_interface(
    equipment_id: int,
    payload: EquipmentInterfaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentInterfaceRead:
    with _registry_transaction(db):
        interface = create_interface(
            db, equipment_id=equipment_id, payload=payload, user=current_user
        )
    db.refresh(interface)
    return _interface_read(interface)


@router.patch("/interfaces/{interface_id}", response_model=EquipmentInterfaceRead)
def patch_equipment_interface(
    interface_id: int,
    payload: EquipmentInterfaceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentInterfaceRead:
    with _registry_transaction(db):
        interface = update_interface(
            db, interface_id=interface_id, payload=payload, user=current_user
        )
    db.refresh(interface)
    return _interface_read(interface)


@router.post(
    "/interfaces/{interface_id}/enable",
    response_model=EquipmentInterfaceRead,
)
def enable_equipment_interface(
    interface_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentInterfaceRead:
    with _registry_transaction(db):
        interface, _assessment = enable_interface(db, interface_id=interface_id, user=current_user)
    db.refresh(interface)
    return _interface_read(interface)


@router.post(
    "/interfaces/{interface_id}/disable",
    response_model=EquipmentInterfaceRead,
)
def disable_equipment_interface(
    interface_id: int,
    payload: EquipmentActionReason,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> EquipmentInterfaceRead:
    with _registry_transaction(db):
        interface = disable_interface(
            db,
            interface_id=interface_id,
            user=current_user,
            reason=payload.reason.value,
        )
    db.refresh(interface)
    return _interface_read(interface)


@router.get("/{equipment_id}/readiness", response_model=list[EquipmentReadinessRead])
def get_equipment_readiness(
    equipment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_officer),
) -> list[EquipmentReadinessRead]:
    _equipment_or_404(db, equipment_id)
    interfaces = (
        db.query(EquipmentInterface)
        .filter(EquipmentInterface.equipment_id == equipment_id)
        .order_by(EquipmentInterface.id)
        .all()
    )
    return [_readiness_read(assess_interface_readiness(db, interface)) for interface in interfaces]


@router.get("/{equipment_id}/documents", response_model=list[EquipmentDocumentRead])
def list_documents(
    equipment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_officer),
) -> list[EquipmentDocumentRead]:
    _equipment_or_404(db, equipment_id)
    documents = (
        db.query(EquipmentDocument)
        .filter(EquipmentDocument.equipment_id == equipment_id)
        .order_by(EquipmentDocument.id)
        .all()
    )
    return [_document_read(document) for document in documents]


@router.post(
    "/{equipment_id}/documents",
    response_model=EquipmentDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_equipment_document(
    equipment_id: int,
    payload: EquipmentDocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentDocumentRead:
    with _registry_transaction(db):
        document = register_document(
            db, equipment_id=equipment_id, payload=payload, user=current_user
        )
    db.refresh(document)
    return _document_read(document)


@router.patch("/documents/{document_id}", response_model=EquipmentDocumentRead)
def patch_equipment_document(
    document_id: int,
    payload: EquipmentDocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentDocumentRead:
    with _registry_transaction(db):
        document = update_document(db, document_id=document_id, payload=payload, user=current_user)
    db.refresh(document)
    return _document_read(document)


@router.get(
    "/{equipment_id}/qualifications",
    response_model=list[EquipmentQualificationRead],
)
def list_qualifications(
    equipment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_officer),
) -> list[EquipmentQualification]:
    _equipment_or_404(db, equipment_id)
    return (
        db.query(EquipmentQualification)
        .filter(EquipmentQualification.equipment_id == equipment_id)
        .order_by(EquipmentQualification.version.desc())
        .all()
    )


@router.post(
    "/{equipment_id}/qualifications",
    response_model=EquipmentQualificationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_equipment_qualification(
    equipment_id: int,
    payload: EquipmentQualificationDraftCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentQualification:
    with _registry_transaction(db):
        qualification = create_qualification_draft(
            db,
            equipment_id=equipment_id,
            payload=payload,
            user=current_user,
        )
    db.refresh(qualification)
    return qualification


@router.patch(
    "/qualifications/{qualification_id}",
    response_model=EquipmentQualificationRead,
)
def patch_equipment_qualification(
    qualification_id: int,
    payload: EquipmentQualificationDraftUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentQualification:
    with _registry_transaction(db):
        qualification = update_qualification_draft(
            db,
            qualification_id=qualification_id,
            payload=payload,
            user=current_user,
        )
    db.refresh(qualification)
    return qualification


@router.post(
    "/qualifications/{qualification_id}/technical-status",
    response_model=EquipmentQualificationRead,
)
def transition_equipment_qualification_technical_status(
    qualification_id: int,
    payload: EquipmentQualificationTechnicalTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentQualification:
    with _registry_transaction(db):
        qualification = transition_qualification_technical_status(
            db,
            qualification_id=qualification_id,
            target_status=payload.status,
            user=current_user,
        )
    db.refresh(qualification)
    return qualification


@router.post(
    "/qualifications/{qualification_id}/analytes",
    response_model=EquipmentApprovedAnalyteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_equipment_approved_analyte(
    qualification_id: int,
    payload: EquipmentApprovedAnalyteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentApprovedAnalyteRead:
    with _registry_transaction(db):
        analyte = add_approved_analyte(
            db,
            qualification_id=qualification_id,
            payload=payload,
            user=current_user,
        )
    db.refresh(analyte)
    return EquipmentApprovedAnalyteRead.model_validate(analyte)


@router.patch(
    "/qualifications/{qualification_id}/analytes/{analyte_id}",
    response_model=EquipmentApprovedAnalyteRead,
)
def patch_equipment_approved_analyte(
    qualification_id: int,
    analyte_id: int,
    payload: EquipmentApprovedAnalyteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentApprovedAnalyteRead:
    with _registry_transaction(db):
        analyte = update_approved_analyte(
            db,
            qualification_id=qualification_id,
            analyte_id=analyte_id,
            payload=payload,
            user=current_user,
        )
    db.refresh(analyte)
    return EquipmentApprovedAnalyteRead.model_validate(analyte)


@router.post(
    "/qualifications/{qualification_id}/submit",
    response_model=EquipmentQualificationRead,
)
def submit_equipment_qualification(
    qualification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentQualification:
    with _registry_transaction(db):
        qualification = submit_qualification(
            db, qualification_id=qualification_id, user=current_user
        )
    db.refresh(qualification)
    return qualification


@router.post(
    "/qualifications/{qualification_id}/approve",
    response_model=EquipmentQualificationRead,
)
def approve_equipment_qualification(
    qualification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> EquipmentQualification:
    with _registry_transaction(db):
        qualification = approve_qualification(
            db, qualification_id=qualification_id, user=current_user
        )
    db.refresh(qualification)
    return qualification


@router.post(
    "/qualifications/{qualification_id}/new-version",
    response_model=EquipmentQualificationRead,
    status_code=status.HTTP_201_CREATED,
)
def new_equipment_qualification_version(
    qualification_id: int,
    payload: EquipmentQualificationNewVersion,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EquipmentQualification:
    with _registry_transaction(db):
        qualification = create_new_qualification_version(
            db,
            qualification_id=qualification_id,
            payload=payload,
            user=current_user,
        )
    db.refresh(qualification)
    return qualification


@router.post(
    "/qualifications/{qualification_id}/suspend",
    response_model=EquipmentQualificationRead,
)
def suspend_equipment_qualification(
    qualification_id: int,
    payload: EquipmentActionReason,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> EquipmentQualification:
    with _registry_transaction(db):
        qualification = suspend_qualification(
            db,
            qualification_id=qualification_id,
            user=current_user,
            reason=payload.reason.value,
        )
    db.refresh(qualification)
    return qualification
