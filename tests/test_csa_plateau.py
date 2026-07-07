import datetime as dt

import app.db.session as db_session
from app.models import CsaExamMapping, CsaPatientLink, CsaPrescriptionLink, ExamOrder, User
from app.services.csa_plateau import import_prescription_event


def _admin_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _contract() -> dict:
    return {
        "patient": {
            "source_patient_id": "CSA-TEST-001",
            "family_name": "PATIENT",
            "given_names": "TEST",
            "birth_date": "1990-01-01",
            "sex": "F",
        },
        "prescription": {
            "source_prescription_id": "RX-TEST-001",
            "source_patient_id": "CSA-TEST-001",
            "ordered_at": dt.datetime(2026, 7, 1, 9, 0).isoformat(),
            "priority": "routine",
            "exams": [{"code": "NFS", "display": "Numération formule sanguine"}],
        },
    }


def test_csa_status_is_protected_and_transport_is_disabled(client) -> None:
    assert client.get("/api/v1/csa-plateau/status").status_code == 401
    response = client.get("/api/v1/csa-plateau/status", headers=_admin_headers(client))
    assert response.status_code == 200
    assert response.json()["transport_available"] is False
    assert response.json()["operational"] is False


def test_contract_test_is_local_idempotent_and_audited_without_pii(client) -> None:
    headers = _admin_headers(client)
    first = client.post("/api/v1/csa-plateau/contract-test", json=_contract(), headers=headers)
    second = client.post("/api/v1/csa-plateau/contract-test", json=_contract(), headers=headers)

    assert first.status_code == 200
    assert first.json()["network_call_performed"] is False
    assert first.json()["patient_exchange_performed"] is False
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["idempotency_key"] == first.json()["idempotency_key"]

    audit = client.get(
        "/api/v1/audit-events?event_type=csa_plateau.contract_test",
        headers=headers,
    )
    assert audit.status_code == 200
    assert audit.json()["meta"]["total"] == 1
    serialized = str(audit.json())
    assert "PATIENT" not in serialized
    assert "1990-01-01" not in serialized


def test_contract_rejects_mismatched_patient_reference(client) -> None:
    payload = _contract()
    payload["prescription"]["source_patient_id"] = "CSA-OTHER"
    response = client.post(
        "/api/v1/csa-plateau/contract-test",
        json=payload,
        headers=_admin_headers(client),
    )
    assert response.status_code == 422


def _prescription_event() -> dict:
    return {
        "event_key": "labo_prescriptions:evt-001",
        "item_id": "evt-001",
        "payload": {
            "prescription_id": "LAB-CSA-001",
            "patient_id": "csa-patient-001",
            "dossier_no": "CSA-2607-ABC123",
            "patient_nom": "KONAN AMINATA",
            "date_naissance": "1992-04-03",
            "sexe": "F",
            "examens": [{"code": "CSA-NFS", "nom": "Numération formule sanguine"}],
            "prescripteur_role": "infirmier",
            "prescripteur_nom": "Agent Test",
            "motif": "Fièvre",
            "priorite": "urgent",
        },
    }


def test_import_prescription_creates_identity_link_order_and_is_idempotent(client) -> None:
    del client
    db = db_session.SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        db.add(CsaExamMapping(csa_exam_code="CSA-NFS", ruggylab_exam_code="NFS"))
        db.commit()
        outcome, order_id = import_prescription_event(
            db, _prescription_event(), created_by_id=admin.id
        )
        db.commit()
        assert outcome == "imported"
        order = db.query(ExamOrder).filter(ExamOrder.id == order_id).one()
        assert order.priority == "urgent"
        assert [item.exam_code for item in order.items] == ["NFS"]
        assert db.query(CsaPatientLink).count() == 1
        assert db.query(CsaPrescriptionLink).count() == 1

        replay, replay_order_id = import_prescription_event(
            db, _prescription_event(), created_by_id=admin.id
        )
        assert replay == "replayed"
        assert replay_order_id == order_id
        assert db.query(ExamOrder).count() == 1
    finally:
        db.close()


def test_import_rejects_missing_exam_mapping_without_partial_commit(client) -> None:
    del client
    db = db_session.SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        event = _prescription_event()
        event["payload"]["examens"][0]["code"] = "UNKNOWN"
        try:
            import_prescription_event(db, event, created_by_id=admin.id)
        except ValueError as exc:
            assert "Mapping" in str(exc)
        else:
            raise AssertionError("Une prescription sans mapping doit être refusée.")
        db.rollback()
        assert db.query(CsaPrescriptionLink).count() == 0
    finally:
        db.close()
