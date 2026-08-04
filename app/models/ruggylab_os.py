import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.utils.datetime_utils import utcnow_naive


class UserRole(enum.StrEnum):
    TECHNICIAN = "technician"
    OFFICER = "officer"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"  # comptable / gestion : facturation & paiements, sans clinique


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150))
    role: Mapped[UserRole] = mapped_column(
        # values_callable : stocke les VALEURS du StrEnum (minuscules) et non les
        # NOMS (majuscules). Sans cela, SQLAlchemy écrirait 'ADMIN', rejeté par le
        # type PostgreSQL `userrole` (labels minuscules définis par les migrations).
        Enum(UserRole, name="userrole", values_callable=lambda e: [m.value for m in e]),
        default=UserRole.TECHNICIAN,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Version de sécurité incorporée aux JWT. Toute modification sensible du
    # compte l'incrémente afin d'invalider immédiatement les sessions antérieures.
    auth_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    # Unité / service de rattachement (cloisonnement RBAC des dossiers patient).
    # NULL = agent transversal (accès à tous les dossiers).
    unit: Mapped[str | None] = mapped_column(String(100))

    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="user")
    report_signatures: Mapped[list["ReportSignature"]] = relationship(back_populates="signed_by")


class Equipment(Base):
    __tablename__ = "equipments"
    __table_args__ = (Index("uq_equipments_asset_identifier", "asset_identifier", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True)
    type: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(100))
    last_calibration: Mapped[dt.date | None] = mapped_column(Date)
    manufacturer: Mapped[str | None] = mapped_column(String(150))
    model: Mapped[str | None] = mapped_column(String(150))
    device_family: Mapped[str | None] = mapped_column(String(100))
    firmware_version: Mapped[str | None] = mapped_column(String(100))
    # Réutilise la notion d'unité existante (User.unit / Patient.unit).
    unit: Mapped[str | None] = mapped_column(String(100), index=True)
    clinical_use: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    lifecycle_status: Mapped[str | None] = mapped_column(String(50))
    asset_identifier: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, onupdate=utcnow_naive)

    results: Mapped[list["Result"]] = relationship(back_populates="equipment")
    reagent_ratios: Mapped[list["EquipmentReagentRatio"]] = relationship(
        back_populates="equipment",
        cascade="all, delete-orphan",
    )
    maintenances: Mapped[list["EquipmentMaintenance"]] = relationship(
        back_populates="equipment",
        cascade="all, delete-orphan",
    )
    interfaces: Mapped[list["EquipmentInterface"]] = relationship(
        back_populates="equipment",
        order_by="EquipmentInterface.id",
    )
    qualifications: Mapped[list["EquipmentQualification"]] = relationship(
        back_populates="equipment",
        order_by="EquipmentQualification.version",
    )
    documents: Mapped[list["EquipmentDocument"]] = relationship(
        back_populates="equipment",
        order_by="EquipmentDocument.id",
    )


class EquipmentInterface(Base):
    __tablename__ = "equipment_interfaces"
    __table_args__ = (
        CheckConstraint(
            "interface_type IN "
            "('serial','usb_device','usb_storage','ethernet','file_import',"
            "'manual','proprietary','unknown')",
            name="ck_equipment_interfaces_type",
        ),
        CheckConstraint(
            "direction IN ('inbound','outbound','bidirectional','unknown')",
            name="ck_equipment_interfaces_direction",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stable_identifier: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    interface_type: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    # Référence expurgée vers la configuration externe, jamais une connexion.
    endpoint_reference: Mapped[str | None] = mapped_column(String(255))
    protocol_name: Mapped[str | None] = mapped_column(String(100))
    protocol_version: Mapped[str | None] = mapped_column(String(100))
    driver_name: Mapped[str | None] = mapped_column(String(100))
    driver_version: Mapped[str | None] = mapped_column(String(100))
    configuration_version: Mapped[str | None] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, onupdate=utcnow_naive)
    disabled_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    disable_reason: Mapped[str | None] = mapped_column(String(255))

    equipment: Mapped["Equipment"] = relationship(back_populates="interfaces")
    qualifications: Mapped[list["EquipmentQualification"]] = relationship(
        back_populates="interface",
        order_by="EquipmentQualification.version",
    )


class EquipmentQualification(Base):
    __tablename__ = "equipment_qualifications"
    __table_args__ = (
        UniqueConstraint("equipment_id", "version", name="uq_equipment_qualifications_version"),
        CheckConstraint(
            "status IN "
            "('unqualified','documentation_pending','technical_testing',"
            "'technically_qualified','clinical_review_pending','clinically_approved',"
            "'suspended','expired','retired')",
            name="ck_equipment_qualifications_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    equipment_interface_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_interfaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default="unqualified", server_default="unqualified", nullable=False
    )
    scope_description: Mapped[str] = mapped_column(Text, nullable=False)
    decision_reference: Mapped[str | None] = mapped_column(String(255))
    evidence_reference: Mapped[str | None] = mapped_column(String(255))
    non_clinical_comment: Mapped[str | None] = mapped_column(Text)
    document_ids_snapshot: Mapped[list[int]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    snapshot_manufacturer: Mapped[str | None] = mapped_column(String(150))
    snapshot_model: Mapped[str | None] = mapped_column(String(150))
    snapshot_device_family: Mapped[str | None] = mapped_column(String(100))
    snapshot_firmware_version: Mapped[str | None] = mapped_column(String(100))
    snapshot_interface_type: Mapped[str | None] = mapped_column(String(30))
    snapshot_protocol_name: Mapped[str | None] = mapped_column(String(100))
    snapshot_protocol_version: Mapped[str | None] = mapped_column(String(100))
    snapshot_driver_name: Mapped[str | None] = mapped_column(String(100))
    snapshot_driver_version: Mapped[str | None] = mapped_column(String(100))
    snapshot_configuration_version: Mapped[str | None] = mapped_column(String(100))
    effective_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approver_role: Mapped[str | None] = mapped_column(String(30))
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    suspended_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    suspension_reason: Mapped[str | None] = mapped_column(String(100))
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment_qualifications.id", ondelete="RESTRICT"),
        unique=True,
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    equipment: Mapped["Equipment"] = relationship(back_populates="qualifications")
    interface: Mapped["EquipmentInterface"] = relationship(back_populates="qualifications")
    analytes: Mapped[list["EquipmentApprovedAnalyte"]] = relationship(
        back_populates="qualification",
        order_by="EquipmentApprovedAnalyte.id",
    )
    superseded_by: Mapped["EquipmentQualification | None"] = relationship(
        remote_side=[id],
        foreign_keys=[superseded_by_id],
    )


class EquipmentApprovedAnalyte(Base):
    __tablename__ = "equipment_approved_analytes"
    __table_args__ = (
        UniqueConstraint(
            "qualification_id",
            "analyte_code",
            "method_code",
            "sample_type",
            "unit",
            name="uq_equipment_approved_analytes_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    qualification_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_qualifications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    analyte_code: Mapped[str] = mapped_column(String(100), nullable=False)
    method_code: Mapped[str] = mapped_column(String(100), nullable=False)
    sample_type: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_context: Mapped[str | None] = mapped_column(String(100))
    clinical_catalog_reference: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    metadata_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    qualification: Mapped["EquipmentQualification"] = relationship(back_populates="analytes")


class EquipmentDocument(Base):
    __tablename__ = "equipment_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(150))
    model: Mapped[str | None] = mapped_column(String(150))
    version: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(50))
    document_date: Mapped[dt.date | None] = mapped_column(Date)
    page_count: Mapped[int | None] = mapped_column(Integer)
    physical_copy_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    digital_copy_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    storage_reference: Mapped[str | None] = mapped_column(String(255))
    contains_connectivity_section: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    contains_protocol_specification: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    review_status: Mapped[str | None] = mapped_column(String(50))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    review_date: Mapped[dt.date | None] = mapped_column(Date)
    checksum: Mapped[str | None] = mapped_column(String(128))
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    equipment: Mapped["Equipment"] = relationship(back_populates="documents")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ipp_unique_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    sex: Mapped[str | None] = mapped_column(CHAR(1))
    rank: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(30))
    # Quartier / zone de résidence : cartographie épidémiologique de terrain.
    residence_quarter: Mapped[str | None] = mapped_column(String(150))
    # Unité / service rattaché (cloisonnement RBAC). NULL = pool partagé.
    unit: Mapped[str | None] = mapped_column(String(100))

    samples: Mapped[list["Sample"]] = relationship(back_populates="patient")


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    barcode: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    collection_date: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    received_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    status: Mapped[str | None] = mapped_column(String(50))
    # N° de laboratoire lisible (séquence annuelle AAAA-NNNNNN) pour le registre.
    lab_number: Mapped[str | None] = mapped_column(String(20), index=True)
    # Préleveur (libellé libre : nom de l'agent ayant prélevé).
    collected_by_label: Mapped[str | None] = mapped_column(String(150))
    # Aspect / qualité pré-analytique : conforme | hemolyse | icterique |
    # lipemique | coagule | insuffisant. Distinct du statut (workflow), il
    # conditionne la fiabilité des résultats (interférences analytiques).
    aspect: Mapped[str | None] = mapped_column(String(20))

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
    # Discriminateur de nature du résultat (Flux 3) : distingue les résultats
    # chiffrés des résultats qualitatifs/textuels sans dépendre des clés JSONB.
    # "quantitative" | "qualitative" | "poct" | "analyzer" ; None pour l'historique.
    result_type: Mapped[str | None] = mapped_column(String(30), index=True)
    image_url: Mapped[str | None] = mapped_column(String(255))
    validator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    critical_ack_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    critical_ack_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    delta_exceeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delta_analytes: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    flags: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    is_auto_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    amendment_reason: Mapped[str | None] = mapped_column(String(500))

    # ── Interprétation bioref complémentaire (unification des vocabulaires) ───
    # Champs additifs : ne remplacent pas flags/is_critical, les complètent.
    bioref_status: Mapped[str | None] = mapped_column(String(30))
    bioref_comment: Mapped[str | None] = mapped_column(Text)
    bioref_reference_range: Mapped[str | None] = mapped_column(String(120))
    bioref_source: Mapped[str | None] = mapped_column(String(255))

    # ── Suivi TAT (Turnaround Time) — horodatages de phases (tous optionnels) ──
    exam_code: Mapped[str | None] = mapped_column(String(50), index=True)
    prescribed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    registered_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    collected_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    received_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    analysis_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    analysis_finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    tech_validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    bio_validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    sample: Mapped["Sample"] = relationship(back_populates="results")
    equipment: Mapped["Equipment | None"] = relationship(back_populates="results")
    stock_movements: Mapped[list["StockMovement"]] = relationship(back_populates="result")
    dh36_messages: Mapped[list["DH36InboundMessage"]] = relationship(back_populates="result")
    report_signature: Mapped["ReportSignature | None"] = relationship(back_populates="result")
    report_snapshots: Mapped[list["ReportSnapshot"]] = relationship(back_populates="result")
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
    lot_number: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[dt.date | None] = mapped_column(Date)
    supplier: Mapped[str | None] = mapped_column(String(200))
    equipment_ratios: Mapped[list["EquipmentReagentRatio"]] = relationship(
        back_populates="reagent",
        cascade="all, delete-orphan",
    )
    stock_movements: Mapped[list["StockMovement"]] = relationship(back_populates="reagent")


class EquipmentReagentRatio(Base):
    __tablename__ = "equipment_reagent_ratios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipments.id"), nullable=False)
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
    ratio_id: Mapped[int] = mapped_column(ForeignKey("equipment_reagent_ratios.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    equipment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reagent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    consumption_per_run: Mapped[float] = mapped_column(Float, nullable=False)
    adjustment_factor: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    change_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

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
    preset_id: Mapped[int] = mapped_column(ForeignKey("ratio_presets.id"), nullable=False)
    reagent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    reagent_category: Mapped[str | None] = mapped_column(String(50))
    reagent_unit: Mapped[str] = mapped_column(String(20), nullable=False, default="unit")
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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

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
    received_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)

    result: Mapped["Result | None"] = relationship(back_populates="dh36_messages")


class ReportSignature(Base):
    __tablename__ = "report_signatures"
    __table_args__ = (UniqueConstraint("result_id", name="uq_report_signatures_result_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id"), nullable=False)
    signed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_meaning: Mapped[str] = mapped_column(String(150), nullable=False)
    signed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    revocation_reason: Mapped[str | None] = mapped_column(Text)

    result: Mapped["Result"] = relationship(back_populates="report_signature")
    signed_by: Mapped["User"] = relationship(back_populates="report_signatures")


class ReportSnapshot(Base):
    """Version figée du compte-rendu remis ou vérifiable.

    Le résultat analytique reste la source vivante. Ce snapshot capture le
    contenu médical visible au moment de la libération, pour éviter qu'un PDF
    déjà diffusé ne change silencieusement après correction.
    """

    __tablename__ = "report_snapshots"
    __table_args__ = (
        UniqueConstraint("result_id", "version_number", name="uq_report_snapshot_version"),
        UniqueConstraint("verification_token_hash", name="uq_report_snapshot_verify_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="final", index=True)
    audience: Mapped[str] = mapped_column(String(20), nullable=False, default="clinician")
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    content_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verification_path: Mapped[str] = mapped_column(String(255), nullable=False)
    supersedes_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("report_snapshots.id"))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    revocation_reason: Mapped[str | None] = mapped_column(Text)

    result: Mapped["Result"] = relationship(back_populates="report_snapshots")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    supersedes_snapshot: Mapped["ReportSnapshot | None"] = relationship(
        remote_side=[id],
    )


class ReportDeliveryOutbox(Base):
    """File transactionnelle de diffusion des comptes-rendus.

    Les workers externes peuvent consommer ces lignes pour envoyer un PDF,
    notifier un patient ou transmettre un flux FHIR sans perdre l'événement si
    le serveur web redémarre après le commit.
    """

    __tablename__ = "report_delivery_outbox"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_report_delivery_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    report_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("report_snapshots.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    report_snapshot: Mapped["ReportSnapshot"] = relationship()


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
    queued_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    result: Mapped["Result"] = relationship(back_populates="malaria_analysis_jobs")
    requested_by: Mapped["User | None"] = relationship()


class RefreshToken(Base):
    """Stateful refresh token for session management.

    Tokens are stored as SHA-256 hashes so the raw value is never
    persisted.  Revocation is immediate: set revoked_at and the token
    becomes invalid regardless of its expiry.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship()

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None and self.expires_at > utcnow_naive()


class RevokedToken(Base):
    """Liste de révocation des jetons d'accès (JWT) par ``jti``.

    Un jeton d'accès est sans état (stateless) : pour l'invalider avant son
    expiration (déconnexion, compromission), on enregistre son ``jti`` ici.
    ``get_current_user`` rejette tout jeton dont le ``jti`` figure dans cette
    table tant que ``expires_at`` n'est pas dépassé.
    """

    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class TatTarget(Base):
    """Délai cible (Turnaround Time) par type d'examen biologique.

    ``target_minutes`` = seuil « dans les délais » (vert). Au-delà et jusqu'à
    ``target_minutes * warn_factor`` = retard modéré (orange) ; au-delà = retard
    important (rouge).
    """

    __tablename__ = "tat_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warn_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.5)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class BiologicalCodeMapping(Base):
    """Table de correspondance canonique entre les vocabulaires biologiques.

    Relie ``exam_catalog.exam_code``, ``BiologicalReferenceRange.test_code`` et
    les ``analyte`` (data_points / ReferenceRange / CriticalRange), y compris les
    panels (NFS, IONO…) décomposés en composants via ``component_of``.
    """

    __tablename__ = "biological_code_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    canonical_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    exam_code: Mapped[str | None] = mapped_column(String(50), index=True)
    test_code: Mapped[str | None] = mapped_column(String(50), index=True)
    analyte_code: Mapped[str | None] = mapped_column(String(50), index=True)
    component_of: Mapped[str | None] = mapped_column(String(50), index=True)
    label: Mapped[str | None] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(100))
    specimen_type: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(50))
    is_panel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )


class BiologicalReferenceRange(Base):
    """Référentiel de valeurs biologiques de référence (IFCC/Tietz/OMS…).

    Stratifié par sexe et tranche d'âge, avec bornes normales, seuils critiques,
    texte normal pour les tests qualitatifs, interprétation clinique et source.
    """

    __tablename__ = "biological_reference_ranges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    test_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    specimen: Mapped[str | None] = mapped_column(String(100))
    sex: Mapped[str] = mapped_column(String(20), nullable=False, default="ALL")
    age_min_years: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    age_max_years: Mapped[float] = mapped_column(Float, nullable=False, default=120)
    lower_limit: Mapped[float | None] = mapped_column(Float)
    upper_limit: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(50))
    normal_text: Mapped[str | None] = mapped_column(String(255))
    critical_low: Mapped[float | None] = mapped_column(Float)
    critical_high: Mapped[float | None] = mapped_column(Float)
    interpretation: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CriticalRange(Base):
    """Configurable critical (panic) thresholds for analyte values."""

    __tablename__ = "critical_ranges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    analyte: Mapped[str] = mapped_column(String(50), nullable=False)
    low_critical: Mapped[float | None] = mapped_column(Float)
    high_critical: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QcControl(Base):
    """Control material definition for Westgard / Levey-Jennings QC."""

    __tablename__ = "qc_controls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    analyte: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False, default="Niveau 1")
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    target_mean: Mapped[float] = mapped_column(Float, nullable=False)
    target_sd: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    results: Mapped[list["QcResult"]] = relationship(
        back_populates="control",
        cascade="all, delete-orphan",
    )


class QcResult(Base):
    """Single daily QC measurement with automatic Westgard rule evaluation."""

    __tablename__ = "qc_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    control_id: Mapped[int] = mapped_column(
        ForeignKey("qc_controls.id"), nullable=False, index=True
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    measured_at: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    operator: Mapped[str | None] = mapped_column(String(100))
    violations: Mapped[str | None] = mapped_column(Text)  # JSON list of rule codes
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)

    control: Mapped["QcControl"] = relationship(back_populates="results")


class DeltaCheckRule(Base):
    """Règles de delta-check patient (variation inter-résultats)."""

    __tablename__ = "delta_check_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    analyte: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    delta_pct: Mapped[float | None] = mapped_column(Float)
    delta_abs: Mapped[float | None] = mapped_column(Float)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ReferenceRange(Base):
    """Plages de référence par analyte, sexe et tranche d'âge."""

    __tablename__ = "reference_ranges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    analyte: Mapped[str] = mapped_column(String(50), nullable=False)
    sex: Mapped[str] = mapped_column(String(1), nullable=False, default="*")
    age_min_years: Mapped[float | None] = mapped_column(Float)
    age_max_years: Mapped[float | None] = mapped_column(Float)
    low_normal: Mapped[float | None] = mapped_column(Float)
    high_normal: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NotifConfig(Base):
    """Configuration des alertes pour valeurs critiques non-acquittées."""

    __tablename__ = "notif_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(200))
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AutoValidationConfig(Base):
    """Règle d'auto-validation ISO 15189 §5.8 pour les résultats normaux."""

    __tablename__ = "auto_validation_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Règle par défaut")
    require_all_flags_normal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    require_no_delta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    require_not_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class NonConformity(Base):
    """Non-conformité (NC) — Système de management de la qualité ISO 15189 §4.9.

    Source possible : contrôle qualité, valeur critique, maintenance, ou saisie
    manuelle. Workflow : open → analysis → action → verification → closed.
    """

    __tablename__ = "non_conformities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # source : qc | critical | maintenance | manual | other
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    # severity : minor | major | critical
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="minor")
    # status : open | analysis | action | verification | closed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    # Référence optionnelle à l'entité source (ex. result:42, qc_control:3)
    linked_entity_type: Mapped[str | None] = mapped_column(String(50))
    linked_entity_id: Mapped[str | None] = mapped_column(String(50))
    detected_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    root_cause: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    actions: Mapped[list["CorrectiveAction"]] = relationship(
        back_populates="non_conformity", cascade="all, delete-orphan"
    )


class CorrectiveAction(Base):
    """Action corrective ou préventive (CAPA) liée à une non-conformité — §4.10."""

    __tablename__ = "corrective_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    non_conformity_id: Mapped[int] = mapped_column(
        ForeignKey("non_conformities.id"), nullable=False, index=True
    )
    # action_type : corrective | preventive
    action_type: Mapped[str] = mapped_column(String(20), nullable=False, default="corrective")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    # status : planned | in_progress | done
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    effectiveness_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effectiveness_notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    non_conformity: Mapped["NonConformity"] = relationship(back_populates="actions")


class EquipmentMaintenance(Base):
    """Planification et suivi de maintenance / étalonnage des équipements."""

    __tablename__ = "equipment_maintenances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id"), nullable=False, index=True
    )
    maintenance_type: Mapped[str] = mapped_column(String(30), nullable=False, default="preventive")
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    performed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    performed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    next_due_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    equipment: Mapped["Equipment"] = relationship(back_populates="maintenances")


class MilitaryFacility(Base):
    __tablename__ = "military_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    division: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    bureau: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)


# ─────────────────────────────────────────────────────────────────────────────
# Prescription d'examens (bon de demande d'analyses) — le « fil » du labo
# Le médecin prescrit des examens → l'échantillon est prélevé/rattaché →
# les résultats remontent par examen. La prescription est une AIDE au suivi :
# elle n'est pas indispensable à la saisie des échantillons/résultats.
# ─────────────────────────────────────────────────────────────────────────────


class ExamOrder(Base):
    __tablename__ = "exam_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    prescriber: Mapped[str | None] = mapped_column(String(150))
    # Service demandeur (Urgences, Maternité, Consultation externe…).
    requesting_service: Mapped[str | None] = mapped_column(String(100))
    clinical_info: Mapped[str | None] = mapped_column(Text)
    # routine | urgent | stat
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="routine")
    # prescribed → collected → in_progress → completed | cancelled
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="prescribed", index=True
    )
    ordered_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    # Échantillon rattaché une fois prélevé : c'est le maillon central du fil.
    sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    patient: Mapped["Patient"] = relationship()
    sample: Mapped["Sample | None"] = relationship()
    items: Mapped[list["ExamOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class ExamOrderItem(Base):
    __tablename__ = "exam_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("exam_orders.id"), nullable=False, index=True)
    exam_code: Mapped[str] = mapped_column(String(50), nullable=False)
    exam_label: Mapped[str | None] = mapped_column(String(150))
    # pending | resulted | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Résultat produit pour cet examen (le bout du fil).
    result_id: Mapped[int | None] = mapped_column(ForeignKey("results.id"))

    order: Mapped["ExamOrder"] = relationship(back_populates="items")


# ─────────────────────────────────────────────────────────────────────────────
# Comptabilité — facturation des examens (FCFA), répartition CMU, encaissements
# Données dénormalisées (patient_label) : le comptable n'accède pas aux dossiers.
# ─────────────────────────────────────────────────────────────────────────────


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    # Libellé patient figé sur la facture (le comptable n'a pas accès aux PII).
    patient_label: Mapped[str | None] = mapped_column(String(150))
    exam_order_id: Mapped[int | None] = mapped_column(ForeignKey("exam_orders.id"))
    # INSURED (assuré CNAM) | UNINSURED (non assuré)
    patient_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNINSURED")
    insurance_id: Mapped[str | None] = mapped_column(String(50))

    gross_total_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    net_total_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    cnam_part_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    patient_due_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    paid_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # draft | issued | partially_paid | paid | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="issued", index=True)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Plan de paiement fractionné BNPL (optionnel) : seulement si le patient ne
    # peut pas régler le reste à charge comptant. Référence le plan BNPL créé.
    payment_plan_id: Mapped[int | None] = mapped_column(Integer)

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[list["InvoicePayment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    exam_code: Mapped[str | None] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")


class InvoicePayment(Base):
    __tablename__ = "invoice_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    amount_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # CASH | MOBILE_MONEY | INSURANCE | BNPL
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="CASH")
    reference: Mapped[str | None] = mapped_column(String(100))
    paid_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    received_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")


class ExamTariff(Base):
    """Tarif d'un examen (FCFA), pour la facturation automatique des prescriptions.

    Référentiel éditable (le prix dépend du laboratoire) : sert à pré-remplir les
    lignes de facture générées depuis une prescription d'examens terminée.
    """

    __tablename__ = "exam_tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    price_xof: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
