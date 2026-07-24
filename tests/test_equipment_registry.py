"""Registre Equipment : qualification, activation, RBAC et atomicité."""

from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import session as db_session
from app.models import (
    AuditEvent,
    DH36InboundMessage,
    Equipment,
    EquipmentInterface,
    EquipmentQualification,
)
from tests.equipment_registry_testkit import register_synthetic_qualified_equipment

_TEST_PASSWORD = "SyntheticRolePass123!"


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _admin(client) -> dict[str, str]:
    return _login(client, "admin", "change_me_admin_password")


def _create_role(
    client, admin: dict[str, str], role: str, *, unit: str | None = None
) -> dict[str, str]:
    username = f"equip_{role}_{uuid.uuid4().hex[:8]}"
    payload = {
        "username": username,
        "password": _TEST_PASSWORD,
        "role": role,
    }
    if unit is not None:
        payload["unit"] = unit
    response = client.post("/api/v1/users", headers=admin, json=payload)
    assert response.status_code == 201, response.text
    return _login(client, username, _TEST_PASSWORD)


def _equipment_payload(**overrides):
    payload = {
        "name": "Synthetic analyzer",
        "serial_number": f"SYN-{uuid.uuid4().hex[:8]}",
        "type": "synthetic",
        "location": "test-bench",
        "manufacturer": "Synthetic Manufacturer",
        "model": "Synthetic Model",
        "device_family": "synthetic-family",
        "firmware_version": "test-fw-1",
        "unit": "test-unit",
        "clinical_use": True,
        "lifecycle_status": "testing",
        "asset_identifier": f"asset-{uuid.uuid4().hex[:10]}",
    }
    payload.update(overrides)
    return payload


def _interface_payload(**overrides):
    payload = {
        "interface_type": "file_import",
        "direction": "inbound",
        "endpoint_reference": "synthetic-config-reference",
        "protocol_name": "synthetic-protocol",
        "protocol_version": "test-protocol-1",
        "driver_name": "synthetic-driver",
        "driver_version": "test-driver-1",
        "configuration_version": "test-config-1",
    }
    payload.update(overrides)
    return payload


def _create_equipment_and_interface(client, admin, **equipment_overrides):
    equipment_response = client.post(
        "/api/v1/equipments",
        headers=admin,
        json=_equipment_payload(**equipment_overrides),
    )
    assert equipment_response.status_code == 201, equipment_response.text
    equipment_id = equipment_response.json()["id"]
    interface_response = client.post(
        f"/api/v1/equipments/{equipment_id}/interfaces",
        headers=admin,
        json=_interface_payload(),
    )
    assert interface_response.status_code == 201, interface_response.text
    return equipment_id, interface_response.json()["id"]


def _create_complete_qualification(client, admin, officer=None, *, enable=False):
    equipment_id, interface_id = _create_equipment_and_interface(client, admin)
    document = client.post(
        f"/api/v1/equipments/{equipment_id}/documents",
        headers=admin,
        json={
            "document_title": "Synthetic qualification evidence",
            "document_type": "test-evidence",
            "version": "test-1",
            "digital_copy_available": True,
            "storage_reference": "synthetic-document-reference",
            "contains_connectivity_section": True,
            "contains_protocol_specification": True,
            "review_status": "reviewed",
            "checksum": "a" * 64,
        },
    )
    assert document.status_code == 201, document.text
    qualification = client.post(
        f"/api/v1/equipments/{equipment_id}/qualifications",
        headers=admin,
        json={
            "equipment_interface_id": interface_id,
            "scope_description": "Synthetic non-clinical test scope",
            "expires_at": "2035-01-01T00:00:00",
            "decision_reference": "synthetic-decision-reference",
            "evidence_reference": "synthetic-evidence-reference",
            "document_ids": [document.json()["id"]],
        },
    )
    assert qualification.status_code == 201, qualification.text
    qualification_id = qualification.json()["id"]
    analyte = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/analytes",
        headers=admin,
        json={
            "analyte_code": "SYNTH-A",
            "method_code": "SYNTH-METHOD",
            "sample_type": "synthetic-sample",
            "unit": "synthetic-unit",
            "metadata_version": "test-1",
        },
    )
    assert analyte.status_code == 201, analyte.text
    submitted = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/submit",
        headers=admin,
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/approve",
        headers=officer or admin,
    )
    assert approved.status_code == 200, approved.text
    if enable:
        enabled = client.post(
            f"/api/v1/equipments/interfaces/{interface_id}/enable",
            headers=admin,
        )
        assert enabled.status_code == 200, enabled.text
    return equipment_id, interface_id, qualification_id


def _db_scalar_count(model, *criteria) -> int:
    with db_session.SessionLocal() as db:
        return db.query(model).filter(*criteria).count()


def test_simple_view_is_redacted_and_unit_scoped(client) -> None:
    admin = _admin(client)
    technician = _create_role(client, admin, "technician", unit="test-unit")
    _create_equipment_and_interface(client, admin)

    response = client.get("/api/v1/equipments", headers=technician)

    assert response.status_code == 200, response.text
    item = response.json()[0]
    assert item["readiness_status"] == "unqualified"
    forbidden = {
        "serial_number",
        "serial_number_masked",
        "asset_identifier",
        "endpoint_reference",
        "protocol_name",
        "driver_name",
        "configuration_version",
    }
    assert forbidden.isdisjoint(item)


def test_accountant_has_no_demonstrated_need_for_equipment_view(client) -> None:
    admin = _admin(client)
    accountant = _create_role(client, admin, "accountant")
    assert client.get("/api/v1/equipments", headers=accountant).status_code == 403


def test_officer_reads_details_but_cannot_mutate_identity_or_activate(client) -> None:
    admin = _admin(client)
    officer = _create_role(client, admin, "officer")
    equipment_id, interface_id = _create_equipment_and_interface(client, admin)

    details = client.get(f"/api/v1/equipments/{equipment_id}/details", headers=officer)
    assert details.status_code == 200, details.text
    assert details.json()["serial_number_masked"].startswith("****")
    assert "serial_number" not in details.json()
    assert (
        client.patch(
            f"/api/v1/equipments/{equipment_id}",
            headers=officer,
            json={"manufacturer": "forbidden"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/equipments/interfaces/{interface_id}/enable",
            headers=officer,
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/equipments", {"name": "forbidden"}),
        ("patch", "/api/v1/equipments/1", {"model": "forbidden"}),
        (
            "post",
            "/api/v1/equipments/1/interfaces",
            {"interface_type": "manual", "direction": "inbound"},
        ),
        (
            "post",
            "/api/v1/equipments/1/documents",
            {"document_title": "forbidden", "document_type": "test"},
        ),
        (
            "post",
            "/api/v1/equipments/1/qualifications",
            {
                "equipment_interface_id": 1,
                "scope_description": "forbidden",
            },
        ),
        ("post", "/api/v1/equipments/qualifications/1/approve", None),
        ("post", "/api/v1/equipments/interfaces/1/enable", None),
        (
            "post",
            "/api/v1/equipments/qualifications/1/suspend",
            {"reason": "incident"},
        ),
        (
            "post",
            "/api/v1/equipments/interfaces/1/disable",
            {"reason": "incident"},
        ),
    ],
)
def test_technician_mutations_are_forbidden_without_effect(
    client, method: str, path: str, payload: dict | None
) -> None:
    admin = _admin(client)
    technician = _create_role(client, admin, "technician")
    audit_before = _db_scalar_count(AuditEvent, AuditEvent.event_type.like("equipment.%"))
    response = getattr(client, method)(path, headers=technician, json=payload)
    assert response.status_code == 403, response.text
    assert _db_scalar_count(AuditEvent, AuditEvent.event_type.like("equipment.%")) == audit_before


def test_officer_approves_suspends_and_disables_but_does_not_activate(client) -> None:
    admin = _admin(client)
    officer = _create_role(client, admin, "officer")
    equipment_id, interface_id, qualification_id = _create_complete_qualification(
        client, admin, officer=officer
    )
    assert (
        client.post(
            f"/api/v1/equipments/interfaces/{interface_id}/enable",
            headers=officer,
        ).status_code
        == 403
    )
    enabled = client.post(f"/api/v1/equipments/interfaces/{interface_id}/enable", headers=admin)
    assert enabled.status_code == 200, enabled.text
    suspended = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/suspend",
        headers=officer,
        json={"reason": "incident"},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"
    readiness = client.get(f"/api/v1/equipments/{equipment_id}/readiness", headers=officer)
    assert readiness.json()[0]["enabled"] is False
    assert readiness.json()[0]["readiness_status"] == "suspended"


def test_complete_synthetic_fixture_can_be_enabled_without_external_effect(client) -> None:
    admin = _admin(client)
    equipment_id, interface_id, _qualification_id = _create_complete_qualification(
        client, admin, enable=True
    )
    readiness = client.get(f"/api/v1/equipments/{equipment_id}/readiness", headers=admin)
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()[0]["activatable"] is True
    assert readiness.json()[0]["enabled"] is True
    assert readiness.json()[0]["readiness_status"] == "enabled"
    with db_session.SessionLocal() as db:
        interface = db.get(EquipmentInterface, interface_id)
        assert interface is not None and interface.enabled is True
        audit_types = {
            event_type
            for (event_type,) in db.query(AuditEvent.event_type)
            .filter(AuditEvent.event_type.like("equipment.%"))
            .all()
        }
        assert {
            "equipment.identity.create",
            "equipment.interface.create",
            "equipment.document.register",
            "equipment.qualification.draft_create",
            "equipment.qualification.submit",
            "equipment.qualification.approve",
            "equipment.interface.enable",
        }.issubset(audit_types)
        serial_number = db.get(Equipment, equipment_id).serial_number
        assert serial_number
        assert all(
            serial_number not in (payload or "")
            for (payload,) in db.query(AuditEvent.payload)
            .filter(AuditEvent.event_type.like("equipment.%"))
            .all()
        )


@pytest.mark.parametrize(
    ("equipment_override", "interface_override", "expected_condition"),
    [
        ({"model": "   "}, {}, "model_present"),
        ({}, {"protocol_name": None}, "protocol_name_present"),
        ({}, {"driver_version": None}, "driver_version_present"),
        ({}, {"configuration_version": None}, "configuration_version_present"),
    ],
)
def test_activation_refuses_incomplete_technical_identity(
    client,
    equipment_override: dict,
    interface_override: dict,
    expected_condition: str,
) -> None:
    admin = _admin(client)
    equipment_response = client.post(
        "/api/v1/equipments",
        headers=admin,
        json=_equipment_payload(**equipment_override),
    )
    equipment_id = equipment_response.json()["id"]
    interface_response = client.post(
        f"/api/v1/equipments/{equipment_id}/interfaces",
        headers=admin,
        json=_interface_payload(**interface_override),
    )
    interface_id = interface_response.json()["id"]
    enabled = client.post(f"/api/v1/equipments/interfaces/{interface_id}/enable", headers=admin)
    assert enabled.status_code == 422
    assert expected_condition in enabled.text
    with db_session.SessionLocal() as db:
        assert db.get(EquipmentInterface, interface_id).enabled is False


def test_submit_refuses_qualification_without_approved_analyte(client) -> None:
    admin = _admin(client)
    equipment_id, interface_id = _create_equipment_and_interface(client, admin)
    document = client.post(
        f"/api/v1/equipments/{equipment_id}/documents",
        headers=admin,
        json={
            "document_title": "Synthetic evidence",
            "document_type": "test",
        },
    )
    qualification = client.post(
        f"/api/v1/equipments/{equipment_id}/qualifications",
        headers=admin,
        json={
            "equipment_interface_id": interface_id,
            "scope_description": "Synthetic scope",
            "decision_reference": "synthetic-decision",
            "evidence_reference": "synthetic-evidence",
            "document_ids": [document.json()["id"]],
        },
    )
    response = client.post(
        f"/api/v1/equipments/qualifications/{qualification.json()['id']}/submit",
        headers=admin,
    )
    assert response.status_code == 422
    assert "approved_analyte_scope" in response.text


def test_expired_and_mismatched_qualifications_cannot_enable(client) -> None:
    admin = _admin(client)
    _equipment_id, interface_id, qualification_id = _create_complete_qualification(client, admin)
    with db_session.SessionLocal() as db:
        qualification = db.get(EquipmentQualification, qualification_id)
        qualification.expires_at = dt.datetime(2020, 1, 1)
        db.commit()
    expired = client.post(f"/api/v1/equipments/interfaces/{interface_id}/enable", headers=admin)
    assert expired.status_code == 422
    assert "qualification_not_expired" in expired.text

    with db_session.SessionLocal() as db:
        qualification = db.get(EquipmentQualification, qualification_id)
        qualification.expires_at = dt.datetime(2035, 1, 1)
        db.commit()
    changed = client.patch(
        f"/api/v1/equipments/interfaces/{interface_id}",
        headers=admin,
        json={"driver_version": "changed-test-driver"},
    )
    assert changed.status_code == 200, changed.text
    mismatch = client.post(f"/api/v1/equipments/interfaces/{interface_id}/enable", headers=admin)
    assert mismatch.status_code == 422
    assert "qualification_snapshot_matches" in mismatch.text


def test_approved_qualification_is_immutable_and_new_version_preserves_history(
    client,
) -> None:
    admin = _admin(client)
    _equipment_id, _interface_id, qualification_id = _create_complete_qualification(client, admin)
    update = client.patch(
        f"/api/v1/equipments/qualifications/{qualification_id}",
        headers=admin,
        json={"scope_description": "forbidden in-place change"},
    )
    assert update.status_code == 409
    replacement = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/new-version",
        headers=admin,
        json={"scope_description": "Synthetic replacement scope"},
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["version"] == 2
    assert replacement.json()["status"] == "unqualified"
    with db_session.SessionLocal() as db:
        previous = db.get(EquipmentQualification, qualification_id)
        assert previous.status == "clinically_approved"
        assert previous.superseded_by_id == replacement.json()["id"]
        assert db.query(EquipmentQualification).count() == 2


def test_second_root_draft_cannot_replace_the_effective_qualification(client) -> None:
    admin = _admin(client)
    equipment_id, interface_id, _qualification_id = _create_complete_qualification(
        client, admin, enable=True
    )

    duplicate_root = client.post(
        f"/api/v1/equipments/{equipment_id}/qualifications",
        headers=admin,
        json={
            "equipment_interface_id": interface_id,
            "scope_description": "Synthetic conflicting root draft",
        },
    )

    assert duplicate_root.status_code == 409
    assert duplicate_root.json()["detail"]["code"] == "qualification_version_required"
    readiness = client.get(f"/api/v1/equipments/{equipment_id}/readiness", headers=admin)
    assert readiness.status_code == 200
    assert readiness.json()[0]["readiness_status"] == "enabled"
    assert readiness.json()[0]["enabled"] is True


def test_document_referenced_by_submitted_qualification_is_immutable(client) -> None:
    admin = _admin(client)
    equipment_id, _interface_id, _qualification_id = _create_complete_qualification(client, admin)
    documents = client.get(f"/api/v1/equipments/{equipment_id}/documents", headers=admin)
    assert documents.status_code == 200
    document = documents.json()[0]
    assert document["storage_reference_masked"] == "registered"
    assert "storage_reference" not in document
    assert document["checksum_present"] is True
    update = client.patch(
        f"/api/v1/equipments/documents/{document['id']}",
        headers=admin,
        json={"document_title": "forbidden in-place update"},
    )
    assert update.status_code == 409
    assert update.json()["detail"]["code"] == "document_immutable"


def test_suspension_blocks_generic_ingestion_at_use_time(client) -> None:
    admin = _admin(client)
    equipment_id, interface_id, qualification_id = _create_complete_qualification(
        client, admin, enable=True
    )
    suspended = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/suspend",
        headers=admin,
        json={"reason": "incident"},
    )
    assert suspended.status_code == 200
    with db_session.SessionLocal() as db:
        asset_identifier = db.get(Equipment, equipment_id).asset_identifier
        result_count = (
            db.query(EquipmentInterface)
            .filter(
                EquipmentInterface.id == interface_id,
                EquipmentInterface.enabled.is_(True),
            )
            .count()
        )
        assert result_count == 0

    previous_key = settings.ANALYZER_API_KEY
    previous_ips = list(settings.ANALYZER_ALLOWED_IPS)
    previous_hmac = settings.ANALYZER_HMAC_SECRET
    settings.ANALYZER_API_KEY = "synthetic-registry-key"
    settings.ANALYZER_ALLOWED_IPS = []
    settings.ANALYZER_HMAC_SECRET = None
    try:
        response = client.post(
            "/api/v1/analyzer/results",
            headers={"X-Analyzer-Key": settings.ANALYZER_API_KEY},
            json={
                "analyzer_id": asset_identifier,
                "message_id": "synthetic-suspended-message",
                "sample_barcode": "synthetic-no-sample",
                "data_points": {"SYNTH-A": 1.0},
            },
        )
    finally:
        settings.ANALYZER_API_KEY = previous_key
        settings.ANALYZER_ALLOWED_IPS = previous_ips
        settings.ANALYZER_HMAC_SECRET = previous_hmac
    assert response.status_code == 422
    assert "active et qualifiee" in response.text


def test_suspension_blocks_dh36_before_storing_the_message(client) -> None:
    admin = _admin(client)
    serial = f"SYN-DH36-{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/equipments",
        headers=admin,
        json={"name": "Dymind DH36", "serial_number": serial},
    )
    equipment_id = response.json()["id"]
    with db_session.SessionLocal() as db:
        equipment = db.get(Equipment, equipment_id)
        assert equipment is not None
        _equipment, interface, qualification = register_synthetic_qualified_equipment(
            db,
            equipment=equipment,
            asset_identifier=f"synthetic-dh36-guard-{uuid.uuid4().hex[:8]}",
            analyte_codes={"WBC"},
        )
        interface_id = interface.id
        qualification_id = qualification.id
    suspended = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/suspend",
        headers=admin,
        json={"reason": "incident"},
    )
    assert suspended.status_code == 200
    raw_message = "\r".join(
        [
            f"MSH|^~\\&|{serial}|LAB|RUGGYLAB|LAB|20260724000000||ORU^R01|SYN-GUARD|P|2.3",
            "PID|||SYNTHETIC||Registry^Guard",
            "OBR|1||SYNTHETIC-BARCODE||CBC",
            "OBX|1|NM|WBC||6.1|10^9/L",
        ]
    )
    message_count = _db_scalar_count(DH36InboundMessage)
    response = client.post(
        "/api/v1/dh36/ingest",
        headers=admin,
        json={"raw_message": raw_message},
    )
    assert response.status_code == 422
    assert _db_scalar_count(DH36InboundMessage) == message_count
    with db_session.SessionLocal() as db:
        assert db.get(EquipmentInterface, interface_id).enabled is False


@pytest.mark.parametrize(
    ("path_suffix", "payload"),
    [
        ("", {"name": "Mass assignment", "enabled": True}),
        (
            "/1/interfaces",
            {
                "interface_type": "manual",
                "direction": "inbound",
                "enabled": True,
            },
        ),
        (
            "/1/qualifications",
            {
                "equipment_interface_id": 1,
                "scope_description": "Mass assignment",
                "status": "clinically_approved",
                "approved_at": "2030-01-01T00:00:00",
            },
        ),
    ],
)
def test_mass_assignment_is_rejected(client, path_suffix: str, payload: dict) -> None:
    admin = _admin(client)
    response = client.post(f"/api/v1/equipments{path_suffix}", headers=admin, json=payload)
    assert response.status_code == 422


def test_free_text_action_reason_is_rejected_without_audit(client) -> None:
    admin = _admin(client)
    _equipment_id, interface_id = _create_equipment_and_interface(client, admin)
    audit_before = _db_scalar_count(AuditEvent, AuditEvent.event_type.like("equipment.%"))

    response = client.post(
        f"/api/v1/equipments/interfaces/{interface_id}/disable",
        headers=admin,
        json={"reason": "free text or sensitive value"},
    )

    assert response.status_code == 422
    assert _db_scalar_count(AuditEvent, AuditEvent.event_type.like("equipment.%")) == audit_before


def test_audit_failure_rolls_back_identity_creation(client) -> None:
    admin = _admin(client)
    name = f"Rollback-{uuid.uuid4().hex[:8]}"
    with (
        patch(
            "app.services.equipment_registry.log_audit_event",
            side_effect=RuntimeError("synthetic audit failure"),
        ),
        pytest.raises(RuntimeError, match="synthetic audit failure"),
    ):
        client.post(
            "/api/v1/equipments",
            headers=admin,
            json=_equipment_payload(name=name),
        )
    assert _db_scalar_count(Equipment, Equipment.name == name) == 0


def test_audit_failure_rolls_back_activation_from_a_new_session(client) -> None:
    admin = _admin(client)
    _equipment_id, interface_id, _qualification_id = _create_complete_qualification(client, admin)
    with (
        patch(
            "app.services.equipment_registry.log_audit_event",
            side_effect=RuntimeError("synthetic audit failure"),
        ),
        pytest.raises(RuntimeError, match="synthetic audit failure"),
    ):
        client.post(
            f"/api/v1/equipments/interfaces/{interface_id}/enable",
            headers=admin,
        )
    with db_session.SessionLocal() as db:
        assert db.get(EquipmentInterface, interface_id).enabled is False


def test_commit_failure_rolls_back_identity_update(client) -> None:
    admin = _admin(client)
    equipment_id, _interface_id = _create_equipment_and_interface(client, admin)
    with (
        patch.object(Session, "commit", side_effect=RuntimeError("synthetic commit failure")),
        pytest.raises(RuntimeError, match="synthetic commit failure"),
    ):
        client.patch(
            f"/api/v1/equipments/{equipment_id}",
            headers=admin,
            json={"manufacturer": "must-not-persist"},
        )
    with db_session.SessionLocal() as db:
        equipment = db.get(Equipment, equipment_id)
        assert equipment.manufacturer == "Synthetic Manufacturer"
