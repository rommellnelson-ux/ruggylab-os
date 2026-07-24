"""Régressions concurrentes R6 nécessitant PostgreSQL réel."""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.orm import Session

import app.services.analyzer_ingestion as analyzer_ingestion_service
from app.db.session import SessionLocal, engine
from app.models import (
    AuditEvent,
    DH36InboundMessage,
    Equipment,
    EquipmentApprovedAnalyte,
    EquipmentDocument,
    EquipmentInterface,
    EquipmentQualification,
    EquipmentReagentRatio,
    Patient,
    Reagent,
    Result,
    Sample,
    StockMovement,
    User,
    UserRole,
)
from app.schemas.analyzer import AnalyzerResultIngest
from app.services.analyzer_ingestion import analyzer_idempotency_key, ingest_analyzer_result
from app.services.interfacing.dh36_ingestion import ingest_dh36_message
from tests.equipment_registry_testkit import register_synthetic_qualified_equipment

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ces tests valident les verrous et contraintes sous PostgreSQL.",
)


def _dh36_message(barcode: str, message_id: str, serial: str) -> str:
    return "\r".join(
        [
            f"MSH|^~\\&|{serial}|LAB|RUGGYLAB|LAB|20260429183000||ORU^R01|{message_id}|P|2.3",
            "PID|||SYNTHETIC-R6-PG||Analyzer^Concurrency",
            f"OBR|1||{barcode}||CBC",
            "OBX|1|NM|WBC||6.1|10^9/L",
            "OBX|2|NM|RBC||4.7|10^12/L",
            "OBX|3|NM|HGB||132|g/L",
            "OBX|4|NM|HCT||40|%",
            "OBX|5|NM|MCV||86|fL",
            "OBX|6|NM|MCH||29|pg",
            "OBX|7|NM|MCHC||330|g/L",
            "OBX|8|NM|PLT||250|10^9/L",
        ]
    )


def test_r6_concurrent_analyzer_replay_creates_one_result(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        patient = Patient(
            ipp_unique_id=f"R6-AN-PG-{suffix}",
            first_name="Synthetic",
            last_name="Analyzer",
            birth_date=dt.date(1990, 1, 1),
            sex="F",
        )
        sample = Sample(
            barcode=f"R6-AN-BAR-{suffix}",
            patient=patient,
            status="Recu",
        )
        actor = User(
            username=f"r6-an-actor-{suffix}",
            hashed_password="synthetic-test-hash",
            role=UserRole.ADMIN,
        )
        setup.add_all([patient, sample, actor])
        setup.flush()
        equipment, interface, qualification = register_synthetic_qualified_equipment(
            setup,
            asset_identifier=f"r6-analyzer-{suffix}",
            analyte_codes={"HGB"},
            actor=actor,
        )
        patient_id = patient.id
        sample_id = sample.id
        barcode = sample.barcode
        equipment_id = equipment.id
        interface_id = interface.id
        qualification_id = qualification.id
        actor_id = actor.id

    payload = AnalyzerResultIngest(
        analyzer_id=f"r6-analyzer-{suffix}",
        message_id=f"r6-message-{suffix}",
        sample_barcode=barcode,
        exam_code="NFS",
        data_points={"HGB": {"value": 13.2, "unit": "g/dL"}},
    )
    key = analyzer_idempotency_key(payload)
    lookup_barrier = threading.Barrier(2)
    original_lookup = analyzer_ingestion_service._existing_result_id

    def synchronize_missing_lookup(db: Session, idempotency_key: str) -> int | None:
        existing = original_lookup(db, idempotency_key)
        if existing is None:
            try:
                lookup_barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
        return existing

    monkeypatch.setattr(
        analyzer_ingestion_service,
        "_existing_result_id",
        synchronize_missing_lookup,
    )

    def ingest() -> dict:
        with SessionLocal() as db:
            return ingest_analyzer_result(db, payload)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                future.result(timeout=10) for future in [executor.submit(ingest) for _ in range(2)]
            ]

        assert sorted(outcome["status"] for outcome in outcomes) == ["created", "duplicate"]
        assert len({outcome["result_id"] for outcome in outcomes}) == 1
        with SessionLocal() as verification:
            assert verification.query(Result).filter(Result.sample_id == sample_id).count() == 1
            assert (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "analyzer.result_ingest",
                    AuditEvent.entity_id == key,
                )
                .count()
                == 1
            )
    finally:
        with SessionLocal() as cleanup:
            result_ids = [
                row[0]
                for row in cleanup.query(Result.id).filter(Result.sample_id == sample_id).all()
            ]
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "analyzer.result_ingest",
                AuditEvent.entity_id == key,
            ).delete(synchronize_session=False)
            if result_ids:
                cleanup.query(Result).filter(Result.id.in_(result_ids)).delete(
                    synchronize_session=False
                )
            cleanup.query(Sample).filter(Sample.id == sample_id).delete(synchronize_session=False)
            cleanup.query(Patient).filter(Patient.id == patient_id).delete(
                synchronize_session=False
            )
            cleanup.query(EquipmentApprovedAnalyte).filter(
                EquipmentApprovedAnalyte.qualification_id == qualification_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentQualification).filter(
                EquipmentQualification.id == qualification_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentDocument).filter(
                EquipmentDocument.equipment_id == equipment_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentInterface).filter(EquipmentInterface.id == interface_id).delete(
                synchronize_session=False
            )
            cleanup.query(Equipment).filter(Equipment.id == equipment_id).delete(
                synchronize_session=False
            )
            cleanup.query(User).filter(User.id == actor_id).delete(synchronize_session=False)
            cleanup.commit()


def test_r6_concurrent_dh36_replay_returns_duplicate_and_consumes_once(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        patient = Patient(
            ipp_unique_id=f"R6-DH36-PG-{suffix}",
            first_name="Synthetic",
            last_name="DH36",
            birth_date=dt.date(1990, 1, 1),
            sex="F",
        )
        sample = Sample(
            barcode=f"R6-DH36-BAR-{suffix}",
            patient=patient,
            status="Recu",
        )
        equipment = Equipment(
            name="Dymind DH36",
            serial_number=f"R6-DH36-EQ-{suffix}",
            type="Automate",
        )
        reagent = Reagent(
            name=f"R6 DH36 Reagent {suffix}",
            category="hematology",
            unit="L",
            current_stock=1.0,
            alert_threshold=0.1,
        )
        ratio = EquipmentReagentRatio(
            equipment=equipment,
            reagent=reagent,
            consumption_per_run=0.25,
            adjustment_factor=1.0,
            is_active=True,
        )
        actor = User(
            username=f"r6-dh36-actor-{suffix}",
            hashed_password="synthetic-test-hash",
            role=UserRole.ADMIN,
        )
        setup.add_all([patient, sample, equipment, reagent, ratio, actor])
        setup.flush()
        _equipment, interface, qualification = register_synthetic_qualified_equipment(
            setup,
            equipment=equipment,
            asset_identifier=f"synthetic-r6-dh36-{suffix}",
            analyte_codes={"WBC", "RBC", "HGB", "HCT", "MCV", "MCH", "MCHC", "PLT"},
            actor=actor,
        )
        patient_id = patient.id
        sample_id = sample.id
        equipment_id = equipment.id
        reagent_id = reagent.id
        ratio_id = ratio.id
        interface_id = interface.id
        qualification_id = qualification.id
        actor_id = actor.id
        barcode = sample.barcode
        serial = equipment.serial_number

    raw_message = _dh36_message(barcode, f"R6-DH36-MSG-{suffix}", serial)
    flush_barrier = threading.Barrier(2)
    original_flush = Session.flush

    def synchronize_message_insert(self: Session, *args, **kwargs) -> None:
        if any(isinstance(row, DH36InboundMessage) for row in self.new):
            try:
                flush_barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
        original_flush(self, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", synchronize_message_insert)

    def ingest() -> object:
        with SessionLocal() as db:
            return ingest_dh36_message(db, raw_message=raw_message)

    message_id: int | None = None
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                future.result(timeout=10) for future in [executor.submit(ingest) for _ in range(2)]
            ]

        assert sorted(outcome.duplicate for outcome in outcomes) == [False, True]
        assert len({outcome.message.id for outcome in outcomes}) == 1
        assert len({outcome.message.result_id for outcome in outcomes}) == 1
        message_id = outcomes[0].message.id
        with SessionLocal() as verification:
            assert (
                verification.query(DH36InboundMessage)
                .filter(DH36InboundMessage.id == message_id)
                .count()
                == 1
            )
            assert verification.query(Result).filter(Result.sample_id == sample_id).count() == 1
            assert (
                verification.query(StockMovement)
                .filter(StockMovement.reagent_id == reagent_id)
                .count()
                == 1
            )
            stored_reagent = verification.get(Reagent, reagent_id)
            assert stored_reagent is not None
            assert stored_reagent.current_stock == pytest.approx(0.75)
            assert (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "dh36.message.process",
                    AuditEvent.entity_id == str(message_id),
                )
                .count()
                == 1
            )
            assert (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "dh36.message.duplicate",
                    AuditEvent.entity_id == str(message_id),
                )
                .count()
                == 1
            )
    finally:
        with SessionLocal() as cleanup:
            result_ids = [
                row[0]
                for row in cleanup.query(Result.id).filter(Result.sample_id == sample_id).all()
            ]
            if message_id is not None:
                cleanup.query(AuditEvent).filter(
                    AuditEvent.entity_type == "dh36_inbound_message",
                    AuditEvent.entity_id == str(message_id),
                ).delete(synchronize_session=False)
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "stock.consume",
                AuditEvent.entity_id == str(reagent_id),
            ).delete(synchronize_session=False)
            cleanup.query(DH36InboundMessage).filter(
                DH36InboundMessage.sample_barcode == barcode
            ).delete(synchronize_session=False)
            cleanup.query(StockMovement).filter(StockMovement.reagent_id == reagent_id).delete(
                synchronize_session=False
            )
            if result_ids:
                cleanup.query(Result).filter(Result.id.in_(result_ids)).delete(
                    synchronize_session=False
                )
            cleanup.query(EquipmentReagentRatio).filter(
                EquipmentReagentRatio.id == ratio_id
            ).delete(synchronize_session=False)
            cleanup.query(Sample).filter(Sample.id == sample_id).delete(synchronize_session=False)
            cleanup.query(Patient).filter(Patient.id == patient_id).delete(
                synchronize_session=False
            )
            cleanup.query(EquipmentApprovedAnalyte).filter(
                EquipmentApprovedAnalyte.qualification_id == qualification_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentQualification).filter(
                EquipmentQualification.id == qualification_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentDocument).filter(
                EquipmentDocument.equipment_id == equipment_id
            ).delete(synchronize_session=False)
            cleanup.query(EquipmentInterface).filter(EquipmentInterface.id == interface_id).delete(
                synchronize_session=False
            )
            cleanup.query(Equipment).filter(Equipment.id == equipment_id).delete(
                synchronize_session=False
            )
            cleanup.query(Reagent).filter(Reagent.id == reagent_id).delete(
                synchronize_session=False
            )
            cleanup.query(User).filter(User.id == actor_id).delete(synchronize_session=False)
            cleanup.commit()
