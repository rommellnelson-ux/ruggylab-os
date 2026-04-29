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
