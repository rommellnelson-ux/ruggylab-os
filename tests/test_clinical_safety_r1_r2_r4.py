"""Régressions du lot correctif de sécurité clinique R1, R2 et R4."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.orm import Session

import app.services.report_signing as report_signing_service
from app.db.session import SessionLocal
from app.models import (
    AuditEvent,
    Equipment,
    ExamOrder,
    Reagent,
    ReportDeliveryOutbox,
    ReportSignature,
    ReportSnapshot,
    Result,
    Sample,
    StockMovement,
)


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _auth(client, username: str = "admin", password: str = "change_me_admin_password"):
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(client, admin, *, role: str, unit: str | None, prefix: str):
    username = f"{prefix}_{_uid()}"
    password = "SyntheticPass123!"
    payload = {"username": username, "password": password, "role": role}
    if unit is not None:
        payload["unit"] = unit
    response = client.post("/api/v1/users", headers=admin, json=payload)
    assert response.status_code == 201, response.text
    return _auth(client, username, password)


def _patient(client, headers, *, unit: str | None = None) -> int:
    payload = {
        "ipp_unique_id": f"SAFETY-{_uid()}",
        "first_name": "Synthetic",
        "last_name": "Safety",
        "birth_date": "1990-01-01",
        "sex": "F",
    }
    if unit is not None:
        payload["unit"] = unit
    response = client.post("/api/v1/patients", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _sample(client, headers, patient_id: int | None) -> dict:
    response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": f"SAFETY-{_uid()}", "patient_id": patient_id, "status": "Recu"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _order(client, headers, patient_id: int) -> int:
    response = client.post(
        "/api/v1/exam-orders",
        headers=headers,
        json={"patient_id": patient_id, "exams": [{"exam_code": "NFS"}]},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _order_state(order_id: int) -> tuple:
    with SessionLocal() as db:
        order = db.get(ExamOrder, order_id)
        assert order is not None
        return (
            order.sample_id,
            order.status,
            tuple((item.status, item.result_id) for item in order.items),
            db.query(Result).count(),
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "exam_order.collect",
                AuditEvent.entity_id == str(order_id),
            )
            .count(),
        )


def _assert_collect_refused_without_effect(
    client,
    headers,
    *,
    order_id: int,
    sample_id: int,
    expected_status: int,
) -> None:
    before = _order_state(order_id)
    response = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": sample_id},
    )
    assert response.status_code == expected_status, response.text
    assert _order_state(order_id) == before


def test_r1_rejects_sample_from_another_patient_without_effect(client) -> None:
    headers = _auth(client)
    patient_a = _patient(client, headers)
    patient_b = _patient(client, headers)
    order_id = _order(client, headers, patient_a)
    sample_b = _sample(client, headers, patient_b)

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=sample_b["id"],
        expected_status=422,
    )


def test_r1_rejects_anonymous_sample_without_effect(client) -> None:
    headers = _auth(client)
    order_id = _order(client, headers, _patient(client, headers))
    anonymous_sample = _sample(client, headers, None)

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=anonymous_sample["id"],
        expected_status=422,
    )


def test_r1_rejects_cancelled_order_without_effect(client) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    sample = _sample(client, headers, patient_id)
    collected = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": sample["id"]},
    )
    assert collected.status_code == 200, collected.text
    cancelled = client.patch(
        f"/api/v1/exam-orders/{order_id}",
        headers=headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=sample["id"],
        expected_status=409,
    )


def test_r1_rejects_completed_order_without_effect(client) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    sample = _sample(client, headers, patient_id)
    with SessionLocal() as db:
        order = db.get(ExamOrder, order_id)
        assert order is not None
        order.status = "completed"
        db.commit()

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=sample["id"],
        expected_status=409,
    )


def test_r1_same_sample_is_idempotent(client) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    sample = _sample(client, headers, patient_id)
    first = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": sample["id"]},
    )
    assert first.status_code == 200, first.text
    before = _order_state(order_id)

    second = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": sample["id"]},
    )
    assert second.status_code == 200, second.text
    assert _order_state(order_id) == before


def test_r1_different_sample_conflicts_without_effect(client) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    first_sample = _sample(client, headers, patient_id)
    other_sample = _sample(client, headers, patient_id)
    first = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": first_sample["id"]},
    )
    assert first.status_code == 200, first.text

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=other_sample["id"],
        expected_status=409,
    )


def test_r1_same_patient_links_once_and_audits(client) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    sample = _sample(client, headers, patient_id)

    response = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": sample["id"]},
    )
    assert response.status_code == 200, response.text
    state = _order_state(order_id)
    assert state[0] == sample["id"]
    assert state[1] == "collected"
    assert state[2] == (("pending", None),)
    assert state[3] == 0
    assert state[4] == 1


def test_r1_historical_same_sample_patient_mismatch_is_not_idempotent(client) -> None:
    headers = _auth(client)
    patient_a = _patient(client, headers)
    patient_b = _patient(client, headers)
    order_id = _order(client, headers, patient_a)
    sample_b = _sample(client, headers, patient_b)
    with SessionLocal() as db:
        order = db.get(ExamOrder, order_id)
        assert order is not None
        order.sample_id = sample_b["id"]
        order.status = "collected"
        db.commit()

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=sample_b["id"],
        expected_status=422,
    )


def test_r1_historical_same_sample_without_patient_is_not_idempotent(client) -> None:
    headers = _auth(client)
    order_id = _order(client, headers, _patient(client, headers))
    anonymous_sample = _sample(client, headers, None)
    with SessionLocal() as db:
        order = db.get(ExamOrder, order_id)
        assert order is not None
        order.sample_id = anonymous_sample["id"]
        order.status = "collected"
        db.commit()

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=anonymous_sample["id"],
        expected_status=422,
    )


def test_r1_completed_same_sample_is_read_only_and_returns_coherent_thread(
    client, monkeypatch
) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    sample = _sample(client, headers, patient_id)
    collected = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": sample["id"]},
    )
    assert collected.status_code == 200, collected.text
    result = _post_result(client, headers, sample["id"], exam_code="NFS")
    assert result.status_code == 201, result.text
    synchronized = client.get(f"/api/v1/exam-orders/{order_id}/thread", headers=headers)
    assert synchronized.status_code == 200, synchronized.text
    assert synchronized.json()["status"] == "completed"
    before = _order_state(order_id)

    with monkeypatch.context() as patch:
        patch.setattr(
            Session,
            "commit",
            lambda self: (_ for _ in ()).throw(AssertionError("unexpected commit")),
        )
        repeated = client.post(
            f"/api/v1/exam-orders/{order_id}/collect",
            headers=headers,
            json={"sample_id": sample["id"]},
        )

    assert repeated.status_code == 200, repeated.text
    body = repeated.json()
    assert body["status"] == "completed"
    assert body["resulted_exams"] == 1
    assert body["steps"][0]["status"] == "resulted"
    assert body["steps"][0]["result_id"] == result.json()["id"]
    assert _order_state(order_id) == before


def test_r1_completed_other_sample_conflicts_without_effect(client) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    attached = _sample(client, headers, patient_id)
    other = _sample(client, headers, patient_id)
    assert (
        client.post(
            f"/api/v1/exam-orders/{order_id}/collect",
            headers=headers,
            json={"sample_id": attached["id"]},
        ).status_code
        == 200
    )
    assert _post_result(client, headers, attached["id"], exam_code="NFS").status_code == 201
    assert client.get(f"/api/v1/exam-orders/{order_id}/thread", headers=headers).status_code == 200

    _assert_collect_refused_without_effect(
        client,
        headers,
        order_id=order_id,
        sample_id=other["id"],
        expected_status=409,
    )


def test_r1_idempotent_retry_projects_results_without_persisting_progress(
    client, monkeypatch
) -> None:
    headers = _auth(client)
    patient_id = _patient(client, headers)
    order_id = _order(client, headers, patient_id)
    sample = _sample(client, headers, patient_id)
    assert (
        client.post(
            f"/api/v1/exam-orders/{order_id}/collect",
            headers=headers,
            json={"sample_id": sample["id"]},
        ).status_code
        == 200
    )
    result = _post_result(client, headers, sample["id"], exam_code="NFS")
    assert result.status_code == 201, result.text
    before = _order_state(order_id)
    assert before[1] == "collected"
    assert before[2] == (("pending", None),)

    with monkeypatch.context() as patch:
        patch.setattr(
            Session,
            "commit",
            lambda self: (_ for _ in ()).throw(AssertionError("unexpected commit")),
        )
        repeated = client.post(
            f"/api/v1/exam-orders/{order_id}/collect",
            headers=headers,
            json={"sample_id": sample["id"]},
        )

    assert repeated.status_code == 200, repeated.text
    body = repeated.json()
    assert body["status"] == "completed"
    assert body["resulted_exams"] == 1
    assert body["steps"][0]["status"] == "resulted"
    assert body["steps"][0]["result_id"] == result.json()["id"]
    assert _order_state(order_id) == before


def _result_target(client, admin, *, unit: str) -> tuple[int, int]:
    patient_id = _patient(client, admin, unit=unit)
    sample_id = _sample(client, admin, patient_id)["id"]
    return patient_id, sample_id


def _post_result(client, headers, sample_id: int, *, exam_code: str | None = None):
    payload = {"sample_id": sample_id, "data_points": {"WBC": 5.0}}
    if exam_code is not None:
        payload["exam_code"] = exam_code
    return client.post(
        "/api/v1/results",
        headers=headers,
        json=payload,
    )


def test_r2_technician_same_unit_can_create(client) -> None:
    admin = _auth(client)
    technician = _user(client, admin, role="technician", unit="UNIT-A", prefix="tech")
    _, sample_id = _result_target(client, admin, unit="UNIT-A")
    response = _post_result(client, technician, sample_id)
    assert response.status_code == 201, response.text


def test_r2_cross_unit_technician_is_rejected_before_all_effects(client, monkeypatch) -> None:
    admin = _auth(client)
    technician = _user(client, admin, role="technician", unit="UNIT-A", prefix="tech")
    _, sample_id = _result_target(client, admin, unit="UNIT-B")
    equipment = client.post(
        "/api/v1/equipments",
        headers=admin,
        json={"name": f"Synthetic Analyzer {_uid()}", "serial_number": f"SA-{_uid()}"},
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=admin,
        json={"name": f"Synthetic Reagent {_uid()}", "current_stock": 5.0},
    ).json()
    ratio = client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=admin,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": 1.0,
            "adjustment_factor": 1.0,
        },
    )
    assert ratio.status_code == 201, ratio.text
    notifications: list[tuple] = []
    monkeypatch.setattr(
        "app.services.notification_bus.publish_alert_event",
        lambda *args, **kwargs: notifications.append((args, kwargs)),
    )
    with SessionLocal() as db:
        before_results = db.query(Result).count()
        before_movements = db.query(StockMovement).count()
        before_audits = (
            db.query(AuditEvent).filter(AuditEvent.event_type == "stock.consume").count()
        )
        before_stock = db.get(Reagent, reagent["id"]).current_stock

    response = client.post(
        "/api/v1/results",
        headers=technician,
        json={
            "sample_id": sample_id,
            "equipment_id": equipment["id"],
            "data_points": {"WBC": 99.0},
            "is_critical": True,
        },
    )
    assert response.status_code == 403, response.text
    with SessionLocal() as db:
        assert db.query(Result).count() == before_results
        assert db.query(StockMovement).count() == before_movements
        assert (
            db.query(AuditEvent).filter(AuditEvent.event_type == "stock.consume").count()
            == before_audits
        )
        assert db.get(Reagent, reagent["id"]).current_stock == before_stock
    assert notifications == []


def test_r2_admin_from_other_unit_remains_transversal(client) -> None:
    root_admin = _auth(client)
    unit_admin = _user(client, root_admin, role="admin", unit="UNIT-A", prefix="admin")
    _, sample_id = _result_target(client, root_admin, unit="UNIT-B")
    response = _post_result(client, unit_admin, sample_id)
    assert response.status_code == 201, response.text


def test_r2_officer_from_other_unit_remains_transversal(client) -> None:
    admin = _auth(client)
    officer = _user(client, admin, role="officer", unit="UNIT-A", prefix="officer")
    _, sample_id = _result_target(client, admin, unit="UNIT-B")
    response = _post_result(client, officer, sample_id)
    assert response.status_code == 201, response.text


def test_r2_technician_without_unit_remains_transversal(client) -> None:
    admin = _auth(client)
    technician = _user(client, admin, role="technician", unit=None, prefix="tech")
    _, sample_id = _result_target(client, admin, unit="UNIT-B")
    response = _post_result(client, technician, sample_id)
    assert response.status_code == 201, response.text


def test_r2_limited_technician_can_create_for_sample_without_patient(client) -> None:
    admin = _auth(client)
    technician = _user(client, admin, role="technician", unit="UNIT-A", prefix="tech")
    sample_id = _sample(client, admin, None)["id"]
    response = _post_result(client, technician, sample_id)
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("accountant_unit", ["UNIT-A", "UNIT-B"])
def test_r2_accountant_is_forbidden_before_all_effects(
    client, monkeypatch, accountant_unit: str
) -> None:
    admin = _auth(client)
    accountant = _user(client, admin, role="accountant", unit=accountant_unit, prefix="accountant")
    _, sample_id = _result_target(client, admin, unit="UNIT-A")
    equipment = client.post(
        "/api/v1/equipments",
        headers=admin,
        json={"name": f"Synthetic Analyzer {_uid()}", "serial_number": f"SA-{_uid()}"},
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=admin,
        json={"name": f"Synthetic Reagent {_uid()}", "current_stock": 5.0},
    ).json()
    ratio = client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=admin,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": 1.0,
            "adjustment_factor": 1.0,
        },
    )
    assert ratio.status_code == 201, ratio.text
    notifications: list[tuple] = []
    monkeypatch.setattr(
        "app.services.notification_bus.publish_alert_event",
        lambda *args, **kwargs: notifications.append((args, kwargs)),
    )
    with SessionLocal() as db:
        before_results = db.query(Result).count()
        before_movements = db.query(StockMovement).count()
        before_audits = (
            db.query(AuditEvent).filter(AuditEvent.event_type == "stock.consume").count()
        )
        before_stock = db.get(Reagent, reagent["id"]).current_stock

    clinical_lookups: list[type] = []
    original_query = Session.query

    def track_clinical_queries(self, *entities, **kwargs):
        if any(entity in {Sample, Equipment} for entity in entities):
            clinical_lookups.extend(entity for entity in entities if entity in {Sample, Equipment})
        return original_query(self, *entities, **kwargs)

    monkeypatch.setattr(Session, "query", track_clinical_queries)
    monkeypatch.setattr(
        "app.api.v1.endpoints.results.can_access_patient",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("create_result body executed for accountant")
        ),
    )

    response = client.post(
        "/api/v1/results",
        headers=accountant,
        json={
            "sample_id": sample_id,
            "equipment_id": equipment["id"],
            "data_points": {"WBC": 99.0},
            "is_critical": True,
        },
    )
    assert response.status_code == 403, response.text
    with SessionLocal() as db:
        assert db.query(Result).count() == before_results
        assert db.query(StockMovement).count() == before_movements
        assert (
            db.query(AuditEvent).filter(AuditEvent.event_type == "stock.consume").count()
            == before_audits
        )
        assert db.get(Reagent, reagent["id"]).current_stock == before_stock
    assert notifications == []
    assert clinical_lookups == []


def _signable_result(client, headers) -> int:
    patient_id = _patient(client, headers)
    sample_id = _sample(client, headers, patient_id)["id"]
    response = _post_result(client, headers, sample_id)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _report_state(result_id: int) -> tuple[int, int, int, int, int]:
    with SessionLocal() as db:
        snapshot_ids = [
            row[0]
            for row in db.query(ReportSnapshot.id)
            .filter(ReportSnapshot.result_id == result_id)
            .all()
        ]
        outbox_count = (
            db.query(ReportDeliveryOutbox)
            .filter(ReportDeliveryOutbox.report_snapshot_id.in_(snapshot_ids))
            .count()
            if snapshot_ids
            else 0
        )
        return (
            db.query(ReportSignature).filter(ReportSignature.result_id == result_id).count(),
            len(snapshot_ids),
            outbox_count,
            db.query(AuditEvent)
            .filter(AuditEvent.event_type == "report.sign", AuditEvent.entity_id == str(result_id))
            .count(),
            (
                db.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "report.release",
                    AuditEvent.entity_id.in_([str(snapshot_id) for snapshot_id in snapshot_ids]),
                )
                .count()
                if snapshot_ids
                else 0
            ),
        )


def _report_artifacts(result_id: int) -> dict[str, object]:
    """Relit les artefacts dans une session indépendante de la requête."""
    with SessionLocal() as db:
        signature = db.query(ReportSignature).filter(ReportSignature.result_id == result_id).one()
        snapshot = db.query(ReportSnapshot).filter(ReportSnapshot.result_id == result_id).one()
        outbox = (
            db.query(ReportDeliveryOutbox)
            .filter(ReportDeliveryOutbox.report_snapshot_id == snapshot.id)
            .one()
        )
        sign_audit = (
            db.query(AuditEvent)
            .filter(AuditEvent.event_type == "report.sign", AuditEvent.entity_id == str(result_id))
            .one()
        )
        release_audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "report.release",
                AuditEvent.entity_id == str(snapshot.id),
            )
            .one()
        )
        return {
            "signature_id": signature.id,
            "signature_hash": signature.signature_hash,
            "report_hash": signature.report_hash,
            "snapshot_id": snapshot.id,
            "outbox_payload": outbox.payload,
            "sign_entity_id": sign_audit.entity_id,
            "sign_payload": json.loads(sign_audit.payload or "{}"),
            "release_entity_id": release_audit.entity_id,
            "release_payload": json.loads(release_audit.payload or "{}"),
        }


def _sign(client, headers, result_id: int):
    return client.post(
        f"/api/v1/reports/results/{result_id}/sign",
        headers=headers,
        json={"signature_meaning": "Validation synthétique de sécurité."},
    )


def test_r4_sign_persists_signature_snapshot_outbox_and_both_audits(client) -> None:
    headers = _auth(client)
    result_id = _signable_result(client, headers)
    response = _sign(client, headers, result_id)
    assert response.status_code == 201, response.text
    assert _report_state(result_id) == (1, 1, 1, 1, 1)
    artifacts = _report_artifacts(result_id)
    assert artifacts["sign_entity_id"] == str(result_id)
    assert artifacts["sign_payload"] == {
        "signature_id": artifacts["signature_id"],
        "report_hash": artifacts["report_hash"],
        "signature_hash": artifacts["signature_hash"],
        "signature_meaning": "Validation synthétique de sécurité.",
    }
    assert artifacts["release_entity_id"] == str(artifacts["snapshot_id"])
    assert artifacts["release_payload"] == {
        "result_id": result_id,
        "version_number": 1,
        "status": "final",
        "audience": "clinician",
    }
    assert artifacts["outbox_payload"] == {
        "snapshot_id": artifacts["snapshot_id"],
        "result_id": result_id,
        "version_number": 1,
        "verification_path": artifacts["outbox_payload"]["verification_path"],
    }

    duplicate = _sign(client, headers, result_id)
    assert duplicate.status_code == 409, duplicate.text
    assert _report_state(result_id) == (1, 1, 1, 1, 1)


def test_r4_snapshot_failure_rolls_back_everything_and_retry_succeeds(client, monkeypatch) -> None:
    headers = _auth(client)
    result_id = _signable_result(client, headers)
    with monkeypatch.context() as patch:
        patch.setattr(
            report_signing_service,
            "build_report_snapshot_payload",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("snapshot failure")),
        )
        with pytest.raises(RuntimeError, match="snapshot failure"):
            _sign(client, headers, result_id)
    assert _report_state(result_id) == (0, 0, 0, 0, 0)

    retry = _sign(client, headers, result_id)
    assert retry.status_code == 201, retry.text
    assert _report_state(result_id) == (1, 1, 1, 1, 1)


def test_r4_outbox_failure_rolls_back_everything(client, monkeypatch) -> None:
    headers = _auth(client)
    result_id = _signable_result(client, headers)
    with monkeypatch.context() as patch:
        patch.setattr(
            report_signing_service,
            "ReportDeliveryOutbox",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("outbox failure")),
        )
        with pytest.raises(RuntimeError, match="outbox failure"):
            _sign(client, headers, result_id)
    assert _report_state(result_id) == (0, 0, 0, 0, 0)

    retry = _sign(client, headers, result_id)
    assert retry.status_code == 201, retry.text
    assert _report_state(result_id) == (1, 1, 1, 1, 1)


@pytest.mark.parametrize("event_type", ["report.sign", "report.release"])
def test_r4_audit_failure_rolls_back_and_retry_succeeds(
    client, monkeypatch, event_type: str
) -> None:
    headers = _auth(client)
    result_id = _signable_result(client, headers)
    original_log_audit_event = report_signing_service.log_audit_event

    def fail_selected_audit(db, **kwargs):
        if kwargs["event_type"] == event_type:
            raise RuntimeError(f"{event_type} audit failure")
        return original_log_audit_event(db, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(report_signing_service, "log_audit_event", fail_selected_audit)
        with pytest.raises(RuntimeError, match=f"{event_type} audit failure"):
            _sign(client, headers, result_id)
    assert _report_state(result_id) == (0, 0, 0, 0, 0)

    retry = _sign(client, headers, result_id)
    assert retry.status_code == 201, retry.text
    assert _report_state(result_id) == (1, 1, 1, 1, 1)


def test_r4_outbox_flush_failure_rolls_back_and_retry_succeeds(client, monkeypatch) -> None:
    headers = _auth(client)
    result_id = _signable_result(client, headers)
    original_flush = Session.flush

    def fail_when_outbox_is_pending(self, *args, **kwargs):
        if any(isinstance(row, ReportDeliveryOutbox) for row in self.new):
            raise RuntimeError("outbox flush failure")
        return original_flush(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "flush", fail_when_outbox_is_pending)
        with pytest.raises(RuntimeError, match="outbox flush failure"):
            _sign(client, headers, result_id)
    assert _report_state(result_id) == (0, 0, 0, 0, 0)

    retry = _sign(client, headers, result_id)
    assert retry.status_code == 201, retry.text
    assert _report_state(result_id) == (1, 1, 1, 1, 1)


def test_r4_final_commit_failure_rolls_back_and_retry_succeeds(client, monkeypatch) -> None:
    headers = _auth(client)
    result_id = _signable_result(client, headers)

    with monkeypatch.context() as patch:
        patch.setattr(
            Session,
            "commit",
            lambda self: (_ for _ in ()).throw(RuntimeError("final commit failure")),
        )
        with pytest.raises(RuntimeError, match="final commit failure"):
            _sign(client, headers, result_id)
    assert _report_state(result_id) == (0, 0, 0, 0, 0)

    retry = _sign(client, headers, result_id)
    assert retry.status_code == 201, retry.text
    assert _report_state(result_id) == (1, 1, 1, 1, 1)


def test_r4_commit_is_last_database_interaction(client, monkeypatch) -> None:
    headers = _auth(client)
    result_id = _signable_result(client, headers)
    original_commit = Session.commit
    original_execute = Session._execute_internal
    original_flush = Session.flush
    original_refresh = Session.refresh
    committed_sessions: set[int] = set()
    operations: list[str] = []

    def tracked_commit(self):
        result = original_commit(self)
        committed_sessions.add(id(self))
        operations.append("commit")
        return result

    def forbid_execute_after_commit(self, *args, **kwargs):
        if id(self) in committed_sessions:
            raise AssertionError("SQL execution after final commit")
        operations.append("execute")
        return original_execute(self, *args, **kwargs)

    def forbid_flush_after_commit(self, *args, **kwargs):
        if id(self) in committed_sessions:
            raise AssertionError("flush after final commit")
        operations.append("flush")
        return original_flush(self, *args, **kwargs)

    def forbid_refresh_after_commit(self, *args, **kwargs):
        if id(self) in committed_sessions:
            raise AssertionError("refresh after final commit")
        operations.append("refresh")
        return original_refresh(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", tracked_commit)
        patch.setattr(Session, "_execute_internal", forbid_execute_after_commit)
        patch.setattr(Session, "flush", forbid_flush_after_commit)
        patch.setattr(Session, "refresh", forbid_refresh_after_commit)
        response = _sign(client, headers, result_id)

    assert response.status_code == 201, response.text
    assert operations[-1] == "commit"
    assert _report_state(result_id) == (1, 1, 1, 1, 1)
