"""Preuves transactionnelles du registre Equipment nécessitant PostgreSQL."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db import session as db_session
from app.models import (
    AuditEvent,
    Equipment,
    EquipmentApprovedAnalyte,
    EquipmentDocument,
    EquipmentInterface,
    EquipmentQualification,
    User,
    UserRole,
)
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentInterfaceCreate,
    EquipmentQualificationDraftCreate,
    EquipmentQualificationNewVersion,
)
from app.services.equipment_registry import (
    create_equipment,
    create_interface,
    create_new_qualification_version,
    create_qualification_draft,
)
from tests.equipment_registry_testkit import register_synthetic_qualified_equipment

pytestmark = pytest.mark.skipif(
    db_session.engine.dialect.name != "postgresql",
    reason="Ces tests valident la transaction du registre sous PostgreSQL.",
)


def test_equipment_registry_audit_and_identity_are_atomic_on_postgresql() -> None:
    marker = uuid.uuid4().hex
    with db_session.SessionLocal() as db:
        admin = User(
            username=f"equipment-registry-pg-{marker}",
            hashed_password="synthetic-test-hash",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
        admin_id = admin.id
        equipment = create_equipment(
            db,
            payload=EquipmentCreate(
                name=f"Synthetic PG {marker}",
                asset_identifier=f"pg-asset-{marker}",
            ),
            user=admin,
        )
        interface = create_interface(
            db,
            equipment_id=equipment.id,
            payload=EquipmentInterfaceCreate(
                interface_type="file_import",
                direction="inbound",
            ),
            user=admin,
        )
        equipment_id = equipment.id
        interface_id = interface.id
        db.rollback()

    with db_session.SessionLocal() as verification:
        assert verification.get(Equipment, equipment_id) is None
        assert verification.get(EquipmentInterface, interface_id) is None
        assert (
            verification.query(Equipment)
            .filter(Equipment.asset_identifier == f"pg-asset-{marker}")
            .first()
            is None
        )
        verification.query(User).filter(User.id == admin_id).delete(synchronize_session=False)
        verification.commit()


def test_qualification_version_allocation_is_serialized_per_equipment() -> None:
    marker = uuid.uuid4().hex
    with db_session.SessionLocal() as setup:
        actor = User(
            username=f"equipment-version-pg-{marker}",
            hashed_password="synthetic-test-hash",
            role=UserRole.ADMIN,
        )
        setup.add(actor)
        setup.flush()
        equipment, interface, first = register_synthetic_qualified_equipment(
            setup,
            asset_identifier=f"pg-version-asset-{marker}",
            analyte_codes={"SYNTHETIC"},
            actor=actor,
        )
        actor_id = actor.id
        equipment_id = equipment.id
        interface_id = interface.id
        first_id = first.id

    with db_session.SessionLocal() as setup:
        actor = setup.get(User, actor_id)
        assert actor is not None
        second = create_qualification_draft(
            setup,
            equipment_id=equipment_id,
            payload=EquipmentQualificationDraftCreate(
                equipment_interface_id=interface_id,
                scope_description="SYNTHETIC TEST ONLY second source version",
            ),
            user=actor,
        )
        setup.commit()
        second_id = second.id

    first_allocated = threading.Event()
    release_first = threading.Event()

    def allocate(qualification_id: int, *, hold_transaction: bool) -> int:
        with db_session.SessionLocal() as db:
            actor = db.get(User, actor_id)
            assert actor is not None
            replacement = create_new_qualification_version(
                db,
                qualification_id=qualification_id,
                payload=EquipmentQualificationNewVersion(
                    scope_description="SYNTHETIC TEST ONLY concurrent replacement"
                ),
                user=actor,
            )
            if hold_transaction:
                first_allocated.set()
                assert release_first.wait(timeout=5)
            db.commit()
            return replacement.version

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        first_future = executor.submit(allocate, first_id, hold_transaction=True)
        assert first_allocated.wait(timeout=5)
        second_future = executor.submit(allocate, second_id, hold_transaction=False)
        time.sleep(0.25)
        assert not second_future.done(), "la seconde allocation n'a pas attendu le verrou Equipment"
        release_first.set()
        assert sorted([first_future.result(timeout=10), second_future.result(timeout=10)]) == [3, 4]

        with db_session.SessionLocal() as verification:
            versions = [
                row[0]
                for row in verification.query(EquipmentQualification.version)
                .filter(EquipmentQualification.equipment_id == equipment_id)
                .order_by(EquipmentQualification.version)
                .all()
            ]
            assert versions == [1, 2, 3, 4]
    finally:
        release_first.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with db_session.SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(AuditEvent.user_id == actor_id).delete(
                synchronize_session=False
            )
            qualification_ids = [
                row[0]
                for row in cleanup.query(EquipmentQualification.id)
                .filter(EquipmentQualification.equipment_id == equipment_id)
                .all()
            ]
            cleanup.query(EquipmentApprovedAnalyte).filter(
                EquipmentApprovedAnalyte.qualification_id.in_(qualification_ids)
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentQualification).filter(
                EquipmentQualification.equipment_id == equipment_id
            ).update(
                {EquipmentQualification.superseded_by_id: None},
                synchronize_session=False,
            )
            cleanup.flush()
            cleanup.query(EquipmentQualification).filter(
                EquipmentQualification.equipment_id == equipment_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentDocument).filter(
                EquipmentDocument.equipment_id == equipment_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentInterface).filter(
                EquipmentInterface.equipment_id == equipment_id
            ).delete(synchronize_session=False)
            cleanup.query(Equipment).filter(Equipment.id == equipment_id).delete(
                synchronize_session=False
            )
            cleanup.query(User).filter(User.id == actor_id).delete(synchronize_session=False)
            cleanup.commit()
