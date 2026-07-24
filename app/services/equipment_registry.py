"""Registre d'identité, qualification et activation des équipements.

Les fonctions de mutation ajoutent les audits à la session mais ne committent
jamais. Les endpoints gardent ainsi une frontière transactionnelle unique.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Equipment,
    EquipmentApprovedAnalyte,
    EquipmentDocument,
    EquipmentInterface,
    EquipmentQualification,
    User,
)
from app.schemas.equipment import (
    EquipmentApprovedAnalyteCreate,
    EquipmentApprovedAnalyteUpdate,
    EquipmentCreate,
    EquipmentDocumentCreate,
    EquipmentDocumentUpdate,
    EquipmentIdentityUpdate,
    EquipmentInterfaceCreate,
    EquipmentInterfaceUpdate,
    EquipmentQualificationDraftCreate,
    EquipmentQualificationDraftUpdate,
    EquipmentQualificationNewVersion,
    EquipmentQualificationStatus,
    EquipmentReadinessStatus,
)
from app.services.audit import log_audit_event
from app.utils.datetime_utils import utcnow_naive

_DRAFT_STATUSES = {
    EquipmentQualificationStatus.UNQUALIFIED.value,
    EquipmentQualificationStatus.DOCUMENTATION_PENDING.value,
    EquipmentQualificationStatus.TECHNICAL_TESTING.value,
    EquipmentQualificationStatus.TECHNICALLY_QUALIFIED.value,
}
_KNOWN_INTERFACE_TYPES = {
    "serial",
    "usb_device",
    "usb_storage",
    "ethernet",
    "file_import",
    "manual",
    "proprietary",
}
_INBOUND_DIRECTIONS = {"inbound", "bidirectional"}


class EquipmentRegistryError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class EquipmentReadinessAssessment:
    equipment_id: int
    interface_id: int
    activatable: bool
    enabled: bool
    readiness_status: EquipmentReadinessStatus
    satisfied_conditions: tuple[str, ...]
    missing_conditions: tuple[str, ...]
    active_qualification_id: int | None
    active_qualification_version: int | None
    qualification_expires_at: dt.datetime | None
    configuration_version: str | None
    driver_name: str | None
    driver_version: str | None
    protocol_name: str | None
    protocol_version: str | None


def mask_serial_number(value: str | None) -> str | None:
    if not value:
        return None
    suffix = value[-4:] if len(value) > 4 else value[-1:]
    return f"****{suffix}"


def mask_registered_reference(value: str | None) -> str | None:
    return "registered" if value else None


def _audit(
    db: Session,
    *,
    user: User,
    event_type: str,
    entity_type: str,
    entity_id: int,
    version: int | None = None,
    previous_status: str | None = None,
    new_status: str | None = None,
    reason: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "action": event_type,
        "actor_role": user.role.value,
    }
    if version is not None:
        payload["version"] = version
    if previous_status is not None:
        payload["previous_status"] = previous_status
    if new_status is not None:
        payload["new_status"] = new_status
    if reason is not None:
        payload["reason"] = reason
    log_audit_event(
        db,
        user=user,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
    )


def _equipment_or_error(db: Session, equipment_id: int, *, for_update: bool = False) -> Equipment:
    query = db.query(Equipment).filter(Equipment.id == equipment_id)
    if for_update:
        query = query.with_for_update()
    equipment = query.first()
    if equipment is None:
        raise EquipmentRegistryError(
            "equipment_not_found", "Equipement introuvable.", http_status=404
        )
    return equipment


def _interface_or_error(
    db: Session, interface_id: int, *, for_update: bool = False
) -> EquipmentInterface:
    query = db.query(EquipmentInterface).filter(EquipmentInterface.id == interface_id)
    if for_update:
        query = query.with_for_update()
    interface = query.first()
    if interface is None:
        raise EquipmentRegistryError(
            "interface_not_found", "Interface introuvable.", http_status=404
        )
    return interface


def _qualification_or_error(
    db: Session, qualification_id: int, *, for_update: bool = False
) -> EquipmentQualification:
    query = db.query(EquipmentQualification).filter(EquipmentQualification.id == qualification_id)
    if for_update:
        query = query.with_for_update()
    qualification = query.first()
    if qualification is None:
        raise EquipmentRegistryError(
            "qualification_not_found", "Qualification introuvable.", http_status=404
        )
    return qualification


def _validate_document_ids(db: Session, *, equipment_id: int, document_ids: list[int]) -> None:
    if not document_ids:
        return
    unique_ids = set(document_ids)
    count = (
        db.query(func.count(EquipmentDocument.id))
        .filter(
            EquipmentDocument.equipment_id == equipment_id,
            EquipmentDocument.id.in_(unique_ids),
            EquipmentDocument.archived_at.is_(None),
        )
        .scalar()
        or 0
    )
    if count != len(unique_ids):
        raise EquipmentRegistryError(
            "document_scope_invalid",
            "Une reference documentaire ne correspond pas a cet equipement.",
            http_status=422,
        )


def _document_scope_is_valid(db: Session, qualification: EquipmentQualification) -> bool:
    document_ids = set(qualification.document_ids_snapshot)
    if not document_ids:
        return False
    count = (
        db.query(func.count(EquipmentDocument.id))
        .filter(
            EquipmentDocument.equipment_id == qualification.equipment_id,
            EquipmentDocument.id.in_(document_ids),
            EquipmentDocument.archived_at.is_(None),
        )
        .scalar()
        or 0
    )
    return count == len(document_ids)


def create_equipment(db: Session, *, payload: EquipmentCreate, user: User) -> Equipment:
    if payload.serial_number:
        duplicate_serial = (
            db.query(Equipment.id).filter(Equipment.serial_number == payload.serial_number).first()
        )
        if duplicate_serial:
            raise EquipmentRegistryError(
                "serial_number_conflict",
                "Un equipement porte deja ce numero de serie.",
            )
    if payload.asset_identifier:
        duplicate_asset = (
            db.query(Equipment.id)
            .filter(Equipment.asset_identifier == payload.asset_identifier)
            .first()
        )
        if duplicate_asset:
            raise EquipmentRegistryError(
                "asset_identifier_conflict",
                "Un equipement porte deja cet identifiant d'actif.",
            )
    equipment = Equipment(**payload.model_dump())
    db.add(equipment)
    db.flush()
    _audit(
        db,
        user=user,
        event_type="equipment.identity.create",
        entity_type="equipment",
        entity_id=equipment.id,
        new_status=equipment.lifecycle_status,
    )
    return equipment


def _disable_locked_interface(
    db: Session,
    *,
    interface: EquipmentInterface,
    user: User,
    reason: str,
) -> None:
    was_enabled = interface.enabled
    interface.enabled = False
    interface.disabled_at = utcnow_naive()
    interface.disable_reason = reason
    if was_enabled:
        _audit(
            db,
            user=user,
            event_type="equipment.interface.disable",
            entity_type="equipment_interface",
            entity_id=interface.id,
            previous_status="enabled",
            new_status="disabled",
            reason=reason,
        )


def update_equipment_identity(
    db: Session,
    *,
    equipment_id: int,
    payload: EquipmentIdentityUpdate,
    user: User,
) -> Equipment:
    equipment = _equipment_or_error(db, equipment_id, for_update=True)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return equipment
    serial = changes.get("serial_number")
    if serial:
        duplicate_serial = (
            db.query(Equipment.id)
            .filter(Equipment.serial_number == serial, Equipment.id != equipment.id)
            .first()
        )
        if duplicate_serial:
            raise EquipmentRegistryError(
                "serial_number_conflict",
                "Un equipement porte deja ce numero de serie.",
            )
    asset = changes.get("asset_identifier")
    if asset:
        duplicate_asset = (
            db.query(Equipment.id)
            .filter(Equipment.asset_identifier == asset, Equipment.id != equipment.id)
            .first()
        )
        if duplicate_asset:
            raise EquipmentRegistryError(
                "asset_identifier_conflict",
                "Un equipement porte deja cet identifiant d'actif.",
            )
    for key, value in changes.items():
        setattr(equipment, key, value)
    equipment.updated_at = utcnow_naive()
    for interface in (
        db.query(EquipmentInterface)
        .filter(
            EquipmentInterface.equipment_id == equipment.id,
            EquipmentInterface.enabled.is_(True),
        )
        .with_for_update()
        .all()
    ):
        _disable_locked_interface(
            db,
            interface=interface,
            user=user,
            reason="identity_changed",
        )
    _audit(
        db,
        user=user,
        event_type="equipment.identity.update",
        entity_type="equipment",
        entity_id=equipment.id,
        reason="fields:" + ",".join(sorted(changes)),
    )
    return equipment


def create_interface(
    db: Session,
    *,
    equipment_id: int,
    payload: EquipmentInterfaceCreate,
    user: User,
) -> EquipmentInterface:
    _equipment_or_error(db, equipment_id, for_update=True)
    interface = EquipmentInterface(
        equipment_id=equipment_id,
        stable_identifier=str(uuid.uuid4()),
        enabled=False,
        **payload.model_dump(mode="json"),
    )
    db.add(interface)
    db.flush()
    _audit(
        db,
        user=user,
        event_type="equipment.interface.create",
        entity_type="equipment_interface",
        entity_id=interface.id,
        new_status="disabled",
    )
    return interface


def update_interface(
    db: Session,
    *,
    interface_id: int,
    payload: EquipmentInterfaceUpdate,
    user: User,
) -> EquipmentInterface:
    interface = _interface_or_error(db, interface_id, for_update=True)
    changes = payload.model_dump(exclude_unset=True, mode="json")
    if not changes:
        return interface
    _disable_locked_interface(
        db,
        interface=interface,
        user=user,
        reason="interface_configuration_changed",
    )
    for key, value in changes.items():
        setattr(interface, key, value)
    interface.updated_at = utcnow_naive()
    _audit(
        db,
        user=user,
        event_type="equipment.interface.update",
        entity_type="equipment_interface",
        entity_id=interface.id,
        reason="fields:" + ",".join(sorted(changes)),
    )
    return interface


def register_document(
    db: Session,
    *,
    equipment_id: int,
    payload: EquipmentDocumentCreate,
    user: User,
) -> EquipmentDocument:
    _equipment_or_error(db, equipment_id, for_update=True)
    document = EquipmentDocument(
        equipment_id=equipment_id,
        reviewed_by_user_id=user.id if payload.review_status else None,
        **payload.model_dump(),
    )
    db.add(document)
    db.flush()
    _audit(
        db,
        user=user,
        event_type="equipment.document.register",
        entity_type="equipment_document",
        entity_id=document.id,
        new_status=document.review_status,
    )
    return document


def update_document(
    db: Session,
    *,
    document_id: int,
    payload: EquipmentDocumentUpdate,
    user: User,
) -> EquipmentDocument:
    document = (
        db.query(EquipmentDocument)
        .filter(EquipmentDocument.id == document_id)
        .with_for_update()
        .first()
    )
    if document is None:
        raise EquipmentRegistryError("document_not_found", "Document introuvable.", http_status=404)
    referencing_qualifications = (
        db.query(EquipmentQualification)
        .filter(
            EquipmentQualification.equipment_id == document.equipment_id,
            EquipmentQualification.status.notin_(_DRAFT_STATUSES),
        )
        .all()
    )
    if any(
        document.id in qualification.document_ids_snapshot
        for qualification in referencing_qualifications
    ):
        raise EquipmentRegistryError(
            "document_immutable",
            "Un document reference par une qualification soumise est immuable.",
        )
    changes = payload.model_dump(exclude_unset=True)
    archive = changes.pop("archive", None)
    for key, value in changes.items():
        setattr(document, key, value)
    if archive is not None:
        document.archived_at = utcnow_naive() if archive else None
    if "review_status" in changes:
        document.reviewed_by_user_id = user.id
    _audit(
        db,
        user=user,
        event_type="equipment.document.register",
        entity_type="equipment_document",
        entity_id=document.id,
        new_status=document.review_status,
        reason="metadata_update",
    )
    return document


def create_qualification_draft(
    db: Session,
    *,
    equipment_id: int,
    payload: EquipmentQualificationDraftCreate,
    user: User,
) -> EquipmentQualification:
    _equipment_or_error(db, equipment_id, for_update=True)
    interface = _interface_or_error(db, payload.equipment_interface_id, for_update=True)
    if interface.equipment_id != equipment_id:
        raise EquipmentRegistryError(
            "interface_scope_invalid",
            "L'interface ne correspond pas a cet equipement.",
            http_status=422,
        )
    _validate_document_ids(db, equipment_id=equipment_id, document_ids=payload.document_ids)
    current_version = (
        db.query(func.max(EquipmentQualification.version))
        .filter(EquipmentQualification.equipment_id == equipment_id)
        .scalar()
        or 0
    )
    qualification = EquipmentQualification(
        equipment_id=equipment_id,
        equipment_interface_id=interface.id,
        version=current_version + 1,
        status=EquipmentQualificationStatus.UNQUALIFIED.value,
        scope_description=payload.scope_description,
        expires_at=payload.expires_at,
        decision_reference=payload.decision_reference,
        evidence_reference=payload.evidence_reference,
        non_clinical_comment=payload.non_clinical_comment,
        document_ids_snapshot=sorted(set(payload.document_ids)),
        created_by_user_id=user.id,
    )
    db.add(qualification)
    db.flush()
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.draft_create",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        new_status=qualification.status,
    )
    return qualification


def update_qualification_draft(
    db: Session,
    *,
    qualification_id: int,
    payload: EquipmentQualificationDraftUpdate,
    user: User,
) -> EquipmentQualification:
    qualification = _qualification_or_error(db, qualification_id, for_update=True)
    if qualification.status not in _DRAFT_STATUSES:
        raise EquipmentRegistryError(
            "qualification_immutable",
            "Une qualification soumise ou approuvee ne peut pas etre modifiee en place.",
        )
    changes = payload.model_dump(exclude_unset=True)
    document_ids = changes.pop("document_ids", None)
    if document_ids is not None:
        _validate_document_ids(
            db,
            equipment_id=qualification.equipment_id,
            document_ids=document_ids,
        )
        qualification.document_ids_snapshot = sorted(set(document_ids))
    for key, value in changes.items():
        setattr(qualification, key, value)
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.draft_update",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        reason="fields:" + ",".join(sorted(payload.model_fields_set)),
    )
    return qualification


def transition_qualification_technical_status(
    db: Session,
    *,
    qualification_id: int,
    target_status: EquipmentQualificationStatus,
    user: User,
) -> EquipmentQualification:
    qualification = _qualification_or_error(db, qualification_id, for_update=True)
    if qualification.status not in _DRAFT_STATUSES:
        raise EquipmentRegistryError(
            "qualification_immutable",
            "Une qualification soumise ou approuvee ne peut pas etre modifiee en place.",
        )
    previous = qualification.status
    qualification.status = target_status.value
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.draft_update",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        previous_status=previous,
        new_status=qualification.status,
    )
    return qualification


def add_approved_analyte(
    db: Session,
    *,
    qualification_id: int,
    payload: EquipmentApprovedAnalyteCreate,
    user: User,
) -> EquipmentApprovedAnalyte:
    qualification = _qualification_or_error(db, qualification_id, for_update=True)
    if qualification.status not in _DRAFT_STATUSES:
        raise EquipmentRegistryError(
            "qualification_immutable",
            "Le perimetre analytique d'une qualification soumise est immuable.",
        )
    duplicate = (
        db.query(EquipmentApprovedAnalyte.id)
        .filter(
            EquipmentApprovedAnalyte.qualification_id == qualification.id,
            EquipmentApprovedAnalyte.analyte_code == payload.analyte_code,
            EquipmentApprovedAnalyte.method_code == payload.method_code,
            EquipmentApprovedAnalyte.sample_type == payload.sample_type,
            EquipmentApprovedAnalyte.unit == payload.unit,
        )
        .first()
    )
    if duplicate:
        raise EquipmentRegistryError(
            "analyte_scope_conflict",
            "Ce perimetre analytique existe deja pour cette qualification.",
        )
    analyte = EquipmentApprovedAnalyte(
        qualification_id=qualification.id,
        **payload.model_dump(),
    )
    db.add(analyte)
    db.flush()
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.draft_update",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        reason="approved_analyte_added",
    )
    return analyte


def update_approved_analyte(
    db: Session,
    *,
    qualification_id: int,
    analyte_id: int,
    payload: EquipmentApprovedAnalyteUpdate,
    user: User,
) -> EquipmentApprovedAnalyte:
    qualification = _qualification_or_error(db, qualification_id, for_update=True)
    if qualification.status not in _DRAFT_STATUSES:
        raise EquipmentRegistryError(
            "qualification_immutable",
            "Le perimetre analytique d'une qualification soumise est immuable.",
        )
    analyte = (
        db.query(EquipmentApprovedAnalyte)
        .filter(
            EquipmentApprovedAnalyte.id == analyte_id,
            EquipmentApprovedAnalyte.qualification_id == qualification.id,
        )
        .with_for_update()
        .first()
    )
    if analyte is None:
        raise EquipmentRegistryError(
            "analyte_not_found", "Analyte autorise introuvable.", http_status=404
        )
    analyte.active = payload.active
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.draft_update",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        reason="approved_analyte_status_changed",
    )
    return analyte


def _capture_snapshot(
    qualification: EquipmentQualification,
    equipment: Equipment,
    interface: EquipmentInterface,
) -> None:
    qualification.snapshot_manufacturer = equipment.manufacturer
    qualification.snapshot_model = equipment.model
    qualification.snapshot_device_family = equipment.device_family
    qualification.snapshot_firmware_version = equipment.firmware_version
    qualification.snapshot_interface_type = interface.interface_type
    qualification.snapshot_protocol_name = interface.protocol_name
    qualification.snapshot_protocol_version = interface.protocol_version
    qualification.snapshot_driver_name = interface.driver_name
    qualification.snapshot_driver_version = interface.driver_version
    qualification.snapshot_configuration_version = interface.configuration_version


def _submission_missing_conditions(
    qualification: EquipmentQualification,
    equipment: Equipment,
    interface: EquipmentInterface,
) -> list[str]:
    missing: list[str] = []
    checks = {
        "equipment_asset_identifier": equipment.asset_identifier,
        "equipment_manufacturer": equipment.manufacturer,
        "equipment_model": equipment.model,
        "equipment_device_family": equipment.device_family,
        "equipment_firmware_version": equipment.firmware_version,
        "equipment_clinical_use": equipment.clinical_use,
        "known_interface_type": interface.interface_type in _KNOWN_INTERFACE_TYPES,
        "interface_protocol_name": interface.protocol_name,
        "interface_protocol_version": interface.protocol_version,
        "interface_driver_name": interface.driver_name,
        "interface_driver_version": interface.driver_version,
        "interface_configuration_version": interface.configuration_version,
        "decision_reference": qualification.decision_reference,
        "evidence_reference": qualification.evidence_reference,
        "document_reference": bool(qualification.document_ids_snapshot),
        "approved_analyte_scope": any(analyte.active for analyte in qualification.analytes),
    }
    for code, value in checks.items():
        if not value:
            missing.append(code)
    if qualification.expires_at and qualification.expires_at <= utcnow_naive():
        missing.append("qualification_expiry_in_past")
    return missing


def submit_qualification(
    db: Session, *, qualification_id: int, user: User
) -> EquipmentQualification:
    qualification = _qualification_or_error(db, qualification_id, for_update=True)
    if qualification.status not in _DRAFT_STATUSES:
        raise EquipmentRegistryError(
            "qualification_not_draft",
            "Seul un brouillon peut etre soumis a l'approbation.",
        )
    equipment = _equipment_or_error(db, qualification.equipment_id, for_update=True)
    interface = _interface_or_error(db, qualification.equipment_interface_id, for_update=True)
    _validate_document_ids(
        db,
        equipment_id=qualification.equipment_id,
        document_ids=qualification.document_ids_snapshot,
    )
    missing = _submission_missing_conditions(qualification, equipment, interface)
    if missing:
        raise EquipmentRegistryError(
            "qualification_submission_incomplete",
            "Soumission impossible; conditions manquantes: " + ",".join(missing),
            http_status=422,
        )
    previous = qualification.status
    _capture_snapshot(qualification, equipment, interface)
    qualification.status = EquipmentQualificationStatus.CLINICAL_REVIEW_PENDING.value
    qualification.submitted_at = utcnow_naive()
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.submit",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        previous_status=previous,
        new_status=qualification.status,
    )
    return qualification


def _snapshot_matches(
    qualification: EquipmentQualification,
    equipment: Equipment,
    interface: EquipmentInterface,
) -> bool:
    return (
        qualification.snapshot_manufacturer == equipment.manufacturer
        and qualification.snapshot_model == equipment.model
        and qualification.snapshot_device_family == equipment.device_family
        and qualification.snapshot_firmware_version == equipment.firmware_version
        and qualification.snapshot_interface_type == interface.interface_type
        and qualification.snapshot_protocol_name == interface.protocol_name
        and qualification.snapshot_protocol_version == interface.protocol_version
        and qualification.snapshot_driver_name == interface.driver_name
        and qualification.snapshot_driver_version == interface.driver_version
        and qualification.snapshot_configuration_version == interface.configuration_version
    )


def approve_qualification(
    db: Session, *, qualification_id: int, user: User
) -> EquipmentQualification:
    qualification = _qualification_or_error(db, qualification_id, for_update=True)
    if qualification.status != EquipmentQualificationStatus.CLINICAL_REVIEW_PENDING.value:
        raise EquipmentRegistryError(
            "qualification_not_pending_review",
            "La qualification n'attend pas une approbation clinique.",
        )
    equipment = _equipment_or_error(db, qualification.equipment_id, for_update=True)
    interface = _interface_or_error(db, qualification.equipment_interface_id, for_update=True)
    _validate_document_ids(
        db,
        equipment_id=qualification.equipment_id,
        document_ids=qualification.document_ids_snapshot,
    )
    if not _snapshot_matches(qualification, equipment, interface):
        raise EquipmentRegistryError(
            "qualification_snapshot_mismatch",
            "La configuration technique ne correspond plus au snapshot soumis.",
        )
    missing = _submission_missing_conditions(qualification, equipment, interface)
    if missing:
        raise EquipmentRegistryError(
            "qualification_approval_incomplete",
            "Approbation impossible; conditions manquantes: " + ",".join(missing),
            http_status=422,
        )
    now = utcnow_naive()
    qualification.status = EquipmentQualificationStatus.CLINICALLY_APPROVED.value
    qualification.approved_by_user_id = user.id
    qualification.approver_role = user.role.value
    qualification.approved_at = now
    qualification.effective_at = now
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.approve",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        previous_status=EquipmentQualificationStatus.CLINICAL_REVIEW_PENDING.value,
        new_status=qualification.status,
    )
    return qualification


def create_new_qualification_version(
    db: Session,
    *,
    qualification_id: int,
    payload: EquipmentQualificationNewVersion,
    user: User,
) -> EquipmentQualification:
    previous = _qualification_or_error(db, qualification_id, for_update=True)
    if previous.superseded_by_id is not None:
        raise EquipmentRegistryError(
            "qualification_already_superseded",
            "Cette qualification a deja une version de remplacement.",
        )
    _validate_document_ids(
        db,
        equipment_id=previous.equipment_id,
        document_ids=payload.document_ids,
    )
    version = (
        db.query(func.max(EquipmentQualification.version))
        .filter(EquipmentQualification.equipment_id == previous.equipment_id)
        .scalar()
        or previous.version
    ) + 1
    replacement = EquipmentQualification(
        equipment_id=previous.equipment_id,
        equipment_interface_id=previous.equipment_interface_id,
        version=version,
        status=EquipmentQualificationStatus.UNQUALIFIED.value,
        scope_description=payload.scope_description,
        expires_at=payload.expires_at,
        decision_reference=payload.decision_reference,
        evidence_reference=payload.evidence_reference,
        non_clinical_comment=payload.non_clinical_comment,
        document_ids_snapshot=sorted(set(payload.document_ids)),
        created_by_user_id=user.id,
    )
    db.add(replacement)
    db.flush()
    previous.superseded_by_id = replacement.id
    interface = _interface_or_error(db, previous.equipment_interface_id, for_update=True)
    _disable_locked_interface(
        db,
        interface=interface,
        user=user,
        reason="qualification_superseded",
    )
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.draft_create",
        entity_type="equipment_qualification",
        entity_id=replacement.id,
        version=replacement.version,
        new_status=replacement.status,
        reason=f"supersedes:{previous.id}",
    )
    return replacement


def suspend_qualification(
    db: Session,
    *,
    qualification_id: int,
    user: User,
    reason: str,
) -> EquipmentQualification:
    qualification = _qualification_or_error(db, qualification_id, for_update=True)
    if qualification.status in {
        EquipmentQualificationStatus.SUSPENDED.value,
        EquipmentQualificationStatus.RETIRED.value,
    }:
        raise EquipmentRegistryError(
            "qualification_not_suspendable",
            "Cette qualification ne peut pas etre suspendue.",
        )
    previous = qualification.status
    qualification.status = EquipmentQualificationStatus.SUSPENDED.value
    qualification.suspended_at = utcnow_naive()
    qualification.suspension_reason = reason
    interface = _interface_or_error(db, qualification.equipment_interface_id, for_update=True)
    _disable_locked_interface(
        db,
        interface=interface,
        user=user,
        reason="qualification_suspended",
    )
    _audit(
        db,
        user=user,
        event_type="equipment.qualification.suspend",
        entity_type="equipment_qualification",
        entity_id=qualification.id,
        version=qualification.version,
        previous_status=previous,
        new_status=qualification.status,
        reason=reason,
    )
    return qualification


def _current_qualification(
    db: Session, interface: EquipmentInterface
) -> EquipmentQualification | None:
    return (
        db.query(EquipmentQualification)
        .filter(
            EquipmentQualification.equipment_interface_id == interface.id,
            EquipmentQualification.superseded_by_id.is_(None),
            EquipmentQualification.archived.is_(False),
        )
        .order_by(EquipmentQualification.version.desc())
        .first()
    )


def assess_interface_readiness(
    db: Session, interface: EquipmentInterface
) -> EquipmentReadinessAssessment:
    equipment = interface.equipment
    qualification = _current_qualification(db, interface)
    now = utcnow_naive()
    conditions: dict[str, bool] = {
        "equipment_identified": bool(
            equipment.id and equipment.name and equipment.asset_identifier
        ),
        "manufacturer_present": bool(equipment.manufacturer),
        "model_present": bool(equipment.model),
        "device_family_present": bool(equipment.device_family),
        "firmware_present": bool(equipment.firmware_version),
        "clinical_use_declared": equipment.clinical_use,
        "equipment_not_retired": equipment.lifecycle_status != "retired",
        "interface_type_known": interface.interface_type in _KNOWN_INTERFACE_TYPES,
        "interface_not_archived": not interface.archived,
        "protocol_name_present": bool(interface.protocol_name),
        "protocol_version_present": bool(interface.protocol_version),
        "driver_name_present": bool(interface.driver_name),
        "driver_version_present": bool(interface.driver_version),
        "configuration_version_present": bool(interface.configuration_version),
        "qualification_present": qualification is not None,
        "qualification_clinically_approved": bool(
            qualification
            and qualification.status == EquipmentQualificationStatus.CLINICALLY_APPROVED.value
        ),
        "qualification_not_expired": bool(
            qualification and (qualification.expires_at is None or qualification.expires_at > now)
        ),
        "qualification_not_suspended": bool(
            qualification and qualification.status != EquipmentQualificationStatus.SUSPENDED.value
        ),
        "qualification_not_superseded": bool(
            qualification and qualification.superseded_by_id is None
        ),
        "qualification_snapshot_matches": bool(
            qualification and _snapshot_matches(qualification, equipment, interface)
        ),
        "approved_analyte_scope_present": bool(
            qualification and any(analyte.active for analyte in qualification.analytes)
        ),
        "approval_referenced": bool(
            qualification
            and qualification.approved_at
            and qualification.approved_by_user_id
            and qualification.approver_role
            and qualification.decision_reference
        ),
        "evidence_referenced": bool(
            qualification
            and qualification.evidence_reference
            and _document_scope_is_valid(db, qualification)
        ),
    }
    satisfied = tuple(code for code, passed in conditions.items() if passed)
    missing = tuple(code for code, passed in conditions.items() if not passed)
    activatable = not missing
    if qualification and qualification.status == EquipmentQualificationStatus.SUSPENDED.value:
        readiness_status = EquipmentReadinessStatus.SUSPENDED
    elif not qualification:
        readiness_status = EquipmentReadinessStatus.UNQUALIFIED
    elif not qualification.document_ids_snapshot or not qualification.evidence_reference:
        readiness_status = EquipmentReadinessStatus.DOCUMENTATION_MISSING
    elif qualification.status in {
        EquipmentQualificationStatus.TECHNICAL_TESTING.value,
        EquipmentQualificationStatus.TECHNICALLY_QUALIFIED.value,
    }:
        readiness_status = EquipmentReadinessStatus.TECHNICAL_TESTING
    elif qualification.status != EquipmentQualificationStatus.CLINICALLY_APPROVED.value:
        readiness_status = EquipmentReadinessStatus.CLINICAL_APPROVAL_REQUIRED
    elif interface.enabled and activatable:
        readiness_status = EquipmentReadinessStatus.ENABLED
    else:
        readiness_status = EquipmentReadinessStatus.QUALIFIED_DISABLED
    return EquipmentReadinessAssessment(
        equipment_id=equipment.id,
        interface_id=interface.id,
        activatable=activatable,
        enabled=interface.enabled,
        readiness_status=readiness_status,
        satisfied_conditions=satisfied,
        missing_conditions=missing,
        active_qualification_id=qualification.id if qualification else None,
        active_qualification_version=qualification.version if qualification else None,
        qualification_expires_at=qualification.expires_at if qualification else None,
        configuration_version=interface.configuration_version,
        driver_name=interface.driver_name,
        driver_version=interface.driver_version,
        protocol_name=interface.protocol_name,
        protocol_version=interface.protocol_version,
    )


def enable_interface(
    db: Session, *, interface_id: int, user: User
) -> tuple[EquipmentInterface, EquipmentReadinessAssessment]:
    interface = _interface_or_error(db, interface_id, for_update=True)
    assessment = assess_interface_readiness(db, interface)
    if not assessment.activatable:
        raise EquipmentRegistryError(
            "equipment_not_ready",
            "Activation refusee; conditions manquantes: " + ",".join(assessment.missing_conditions),
            http_status=422,
        )
    if interface.enabled:
        raise EquipmentRegistryError("interface_already_enabled", "L'interface est deja active.")
    interface.enabled = True
    interface.disabled_at = None
    interface.disable_reason = None
    interface.updated_at = utcnow_naive()
    _audit(
        db,
        user=user,
        event_type="equipment.interface.enable",
        entity_type="equipment_interface",
        entity_id=interface.id,
        previous_status="disabled",
        new_status="enabled",
        version=assessment.active_qualification_version,
    )
    return interface, assessment


def disable_interface(
    db: Session, *, interface_id: int, user: User, reason: str
) -> EquipmentInterface:
    interface = _interface_or_error(db, interface_id, for_update=True)
    was_enabled = interface.enabled
    _disable_locked_interface(db, interface=interface, user=user, reason=reason)
    if not was_enabled:
        # Une demande explicite est auditée même si le flag était déjà à false.
        _audit(
            db,
            user=user,
            event_type="equipment.interface.disable",
            entity_type="equipment_interface",
            entity_id=interface.id,
            previous_status="disabled",
            new_status="disabled",
            reason=reason,
        )
    return interface


def assert_equipment_interface_usable(
    db: Session,
    *,
    equipment: Equipment,
) -> EquipmentInterface:
    candidates = (
        db.query(EquipmentInterface)
        .filter(
            EquipmentInterface.equipment_id == equipment.id,
            EquipmentInterface.direction.in_(_INBOUND_DIRECTIONS),
            EquipmentInterface.archived.is_(False),
        )
        .with_for_update()
        .all()
    )
    usable: list[EquipmentInterface] = []
    for interface in candidates:
        assessment = assess_interface_readiness(db, interface)
        if interface.enabled and assessment.activatable:
            usable.append(interface)
    if len(usable) != 1:
        code = "equipment_interface_not_usable" if not usable else "equipment_interface_ambiguous"
        raise EquipmentRegistryError(
            code,
            "Aucune interface entrante unique, active et qualifiee ne correspond a l'equipement.",
            http_status=422,
        )
    return usable[0]


def assert_analytes_authorized(
    db: Session,
    *,
    interface: EquipmentInterface,
    analyte_codes: set[str],
) -> None:
    qualification = _current_qualification(db, interface)
    authorized = (
        {analyte.analyte_code for analyte in qualification.analytes if analyte.active}
        if qualification
        else set()
    )
    unexpected = sorted(code for code in analyte_codes if code not in authorized)
    if unexpected:
        raise EquipmentRegistryError(
            "analyte_scope_not_approved",
            "Le message contient un analyte absent du perimetre clinique approuve.",
            http_status=422,
        )


def find_usable_analyzer_equipment(
    db: Session, *, asset_identifier: str
) -> tuple[Equipment, EquipmentInterface]:
    equipment = db.query(Equipment).filter(Equipment.asset_identifier == asset_identifier).first()
    if equipment is None:
        raise EquipmentRegistryError(
            "analyzer_equipment_not_registered",
            "L'identifiant automate ne correspond a aucun equipement enregistre.",
            http_status=422,
        )
    interface = assert_equipment_interface_usable(db, equipment=equipment)
    return equipment, interface
