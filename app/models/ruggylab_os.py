import datetime as dt
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    CHAR,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


def utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class UserRole(str, enum.Enum):
    TECHNICIAN = "technician"
    OFFICER = "officer"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.TECHNICIAN, nullable=False
    )

    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="user")
    report_signatures: Mapped[list["ReportSignature"]] = relationship(
        back_populates="signed_by"
    )


class Equipment(Base):
    __tablename__ = "equipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True)
    type: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(100))
    last_calibration: Mapped[dt.date | None] = mapped_column(Date)

    results: Mapped[list["Result"]] = relationship(back_populates="equipment")
    reagent_ratios: Mapped[list["EquipmentReagentRatio"]] = relationship(
        back_populates="equipment",
        cascade="all, delete-orphan",
    )


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ipp_unique_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    sex: Mapped[str | None] = mapped_column(CHAR(1))
    rank: Mapped[str | None] = mapped_column(String(50))

    samples: Mapped[list["Sample"]] = relationship(back_populates="patient")


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    barcode: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    collection_date: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    received_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    status: Mapped[str | None] = mapped_column(String(50))

    patient: Mapped["Patient | None"] = relationship(back_populates="samples")
    results: Mapped[list["Result"]] = relationship(back_populates="sample")


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), nullable=False)
    equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipments.id"))
    analysis_date: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    data_points: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    image_url: Mapped[str | None] = mapped_column(String(255))
    validator_id: Mapped[int | None] = mapped_column(Integer)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sample: Mapped["Sample"] = relationship(back_populates="results")
    equipment: Mapped["Equipment | None"] = relationship(back_populates="results")
    stock_movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="result"
    )
    dh36_messages: Mapped[list["DH36InboundMessage"]] = relationship(
        back_populates="result"
    )
    report_signature: Mapped["ReportSignature | None"] = relationship(
        back_populates="result"
    )
    malaria_analysis_jobs: Mapped[list["MalariaAnalysisJob"]] = relationship(
        back_populates="result"
    )


class Reagent(Base):
    __tablename__ = "reagents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str | None] = mapped_column(String(50))
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="unit")
    current_stock: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alert_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    equipment_ratios: Mapped[list["EquipmentReagentRatio"]] = relationship(
        back_populates="reagent",
        cascade="all, delete-orphan",
    )
    stock_movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="reagent"
    )


class EquipmentReagentRatio(Base):
    __tablename__ = "equipment_reagent_ratios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id"), nullable=False
    )
    reagent_id: Mapped[int] = mapped_column(ForeignKey("reagents.id"), nullable=False)
    consumption_per_run: Mapped[float] = mapped_column(Float, nullable=False)
    adjustment_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    equipment: Mapped["Equipment"] = relationship(back_populates="reagent_ratios")
    reagent: Mapped["Reagent"] = relationship(back_populates="equipment_ratios")
    versions: Mapped[list["EquipmentReagentRatioVersion"]] = relationship(
        back_populates="ratio",
        cascade="all, delete-orphan",
    )


class EquipmentReagentRatioVersion(Base):
    __tablename__ = "equipment_reagent_ratio_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ratio_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_reagent_ratios.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    equipment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reagent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    consumption_per_run: Mapped[float] = mapped_column(Float, nullable=False)
    adjustment_factor: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    change_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    ratio: Mapped["EquipmentReagentRatio"] = relationship(back_populates="versions")


class RatioPreset(Base):
    __tablename__ = "ratio_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    equipment_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    items: Mapped[list["RatioPresetItem"]] = relationship(back_populates="preset")


class RatioPresetItem(Base):
    __tablename__ = "ratio_preset_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    preset_id: Mapped[int] = mapped_column(
        ForeignKey("ratio_presets.id"), nullable=False
    )
    reagent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    reagent_category: Mapped[str | None] = mapped_column(String(50))
    reagent_unit: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unit"
    )
    consumption_per_run: Mapped[float] = mapped_column(Float, nullable=False)
    adjustment_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    preset: Mapped["RatioPreset"] = relationship(back_populates="items")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    user: Mapped["User | None"] = relationship(back_populates="audit_events")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reagent_id: Mapped[int] = mapped_column(ForeignKey("reagents.id"), nullable=False)
    result_id: Mapped[int | None] = mapped_column(ForeignKey("results.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    quantity_delta: Mapped[float] = mapped_column(Float, nullable=False)
    stock_before: Mapped[float] = mapped_column(Float, nullable=False)
    stock_after: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )

    reagent: Mapped["Reagent"] = relationship(back_populates="stock_movements")
    result: Mapped["Result | None"] = relationship(back_populates="stock_movements")


class DH36InboundMessage(Base):
    __tablename__ = "dh36_inbound_messages"
    __table_args__ = (
        UniqueConstraint("raw_hash", name="uq_dh36_inbound_messages_raw_hash"),
        UniqueConstraint(
            "message_control_id",
            name="uq_dh36_inbound_messages_message_control_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message_control_id: Mapped[str | None] = mapped_column(String(100), index=True)
    sample_barcode: Mapped[str | None] = mapped_column(String(100), index=True)
    equipment_serial: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    result_id: Mapped[int | None] = mapped_column(ForeignKey("results.id"))
    received_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)

    result: Mapped["Result | None"] = relationship(back_populates="dh36_messages")


class ReportSignature(Base):
    __tablename__ = "report_signatures"
    __table_args__ = (
        UniqueConstraint("result_id", name="uq_report_signatures_result_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id"), nullable=False)
    signed_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_meaning: Mapped[str] = mapped_column(String(150), nullable=False)
    signed_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    revocation_reason: Mapped[str | None] = mapped_column(Text)

    result: Mapped["Result"] = relationship(back_populates="report_signature")
    signed_by: Mapped["User"] = relationship(back_populates="report_signatures")


class MalariaAnalysisJob(Base):
    __tablename__ = "malaria_analysis_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id"), nullable=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    image_url: Mapped[str] = mapped_column(String(255), nullable=False)
    prediction_label: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    result: Mapped["Result"] = relationship(back_populates="malaria_analysis_jobs")
    requested_by: Mapped["User | None"] = relationship()
