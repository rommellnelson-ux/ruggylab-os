"""Fixtures synthétiques explicites pour les tests d'ingestion.

Ces helpers n'utilisent aucun appareil, protocole ou périmètre réel. Ils
construisent uniquement, dans la base temporaire du test, le snapshot complet
exigé par le service fail-closed.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.models import (
    Equipment,
    EquipmentApprovedAnalyte,
    EquipmentDocument,
    EquipmentInterface,
    EquipmentQualification,
    User,
)

_SYNTHETIC_LABEL = "SYNTHETIC TEST ONLY"


def register_synthetic_qualified_equipment(
    db: Session,
    *,
    asset_identifier: str,
    analyte_codes: set[str],
    name: str = "Synthetic analyzer",
    serial_number: str | None = None,
    equipment: Equipment | None = None,
    actor: User | None = None,
) -> tuple[Equipment, EquipmentInterface, EquipmentQualification]:
    admin = actor or db.query(User).filter(User.username == "admin").first()
    assert admin is not None
    if equipment is None:
        equipment = Equipment(
            name=name,
            serial_number=serial_number,
            type="synthetic-test",
        )
        db.add(equipment)
    equipment.manufacturer = _SYNTHETIC_LABEL
    equipment.model = _SYNTHETIC_LABEL
    equipment.device_family = "synthetic-test-family"
    equipment.firmware_version = "synthetic-test-firmware"
    equipment.asset_identifier = asset_identifier
    equipment.clinical_use = True
    equipment.lifecycle_status = "testing"
    db.flush()

    interface = EquipmentInterface(
        equipment_id=equipment.id,
        stable_identifier=str(uuid.uuid4()),
        interface_type="file_import",
        direction="inbound",
        protocol_name="synthetic-test-protocol",
        protocol_version="synthetic-test-protocol-version",
        driver_name="synthetic-test-driver",
        driver_version="synthetic-test-driver-version",
        configuration_version="synthetic-test-configuration",
        enabled=True,
    )
    document = EquipmentDocument(
        equipment_id=equipment.id,
        document_title=_SYNTHETIC_LABEL,
        document_type="synthetic-test-evidence",
        digital_copy_available=False,
        review_status="synthetic-test-reviewed",
    )
    db.add_all([interface, document])
    db.flush()

    qualification = EquipmentQualification(
        equipment_id=equipment.id,
        equipment_interface_id=interface.id,
        version=1,
        status="clinically_approved",
        scope_description=_SYNTHETIC_LABEL,
        decision_reference="synthetic-test-decision",
        evidence_reference="synthetic-test-evidence",
        document_ids_snapshot=[document.id],
        snapshot_manufacturer=equipment.manufacturer,
        snapshot_model=equipment.model,
        snapshot_device_family=equipment.device_family,
        snapshot_firmware_version=equipment.firmware_version,
        snapshot_interface_type=interface.interface_type,
        snapshot_protocol_name=interface.protocol_name,
        snapshot_protocol_version=interface.protocol_version,
        snapshot_driver_name=interface.driver_name,
        snapshot_driver_version=interface.driver_version,
        snapshot_configuration_version=interface.configuration_version,
        effective_at=dt.datetime(2026, 1, 1),
        expires_at=dt.datetime(2035, 1, 1),
        created_by_user_id=admin.id,
        approved_by_user_id=admin.id,
        approver_role="admin",
        submitted_at=dt.datetime(2026, 1, 1),
        approved_at=dt.datetime(2026, 1, 1),
    )
    db.add(qualification)
    db.flush()
    db.add_all(
        [
            EquipmentApprovedAnalyte(
                qualification_id=qualification.id,
                analyte_code=code,
                method_code="synthetic-test-method",
                sample_type="synthetic-test-sample",
                unit="synthetic-test-unit",
                metadata_version="synthetic-test-version",
            )
            for code in sorted(analyte_codes)
        ]
    )
    db.commit()
    db.refresh(equipment)
    db.refresh(interface)
    db.refresh(qualification)
    return equipment, interface, qualification
