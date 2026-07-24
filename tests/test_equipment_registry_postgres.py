"""Preuves transactionnelles du registre Equipment nécessitant PostgreSQL."""

from __future__ import annotations

import uuid

import pytest

from app.db import session as db_session
from app.models import Equipment, EquipmentInterface, User, UserRole
from app.schemas.equipment import EquipmentCreate, EquipmentInterfaceCreate
from app.services.equipment_registry import create_equipment, create_interface

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
