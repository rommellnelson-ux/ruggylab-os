"""Registre normalisé des équipements et qualifications.

Revision ID: 20260724_0039
Revises: 20260723_0038
Create Date: 2026-07-24 00:00:39
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260724_0039"
down_revision = "20260723_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("equipments", sa.Column("manufacturer", sa.String(length=150)))
    op.add_column("equipments", sa.Column("model", sa.String(length=150)))
    op.add_column("equipments", sa.Column("device_family", sa.String(length=100)))
    op.add_column("equipments", sa.Column("firmware_version", sa.String(length=100)))
    op.add_column("equipments", sa.Column("unit", sa.String(length=100)))
    op.add_column(
        "equipments",
        sa.Column(
            "clinical_use",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column("equipments", sa.Column("lifecycle_status", sa.String(length=50)))
    op.add_column("equipments", sa.Column("asset_identifier", sa.String(length=100)))
    op.add_column("equipments", sa.Column("updated_at", sa.DateTime()))
    op.create_index("ix_equipments_unit", "equipments", ["unit"])
    op.create_index(
        "uq_equipments_asset_identifier",
        "equipments",
        ["asset_identifier"],
        unique=True,
    )

    op.create_table(
        "equipment_interfaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("stable_identifier", sa.String(length=36), nullable=False),
        sa.Column("interface_type", sa.String(length=30), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("endpoint_reference", sa.String(length=255)),
        sa.Column("protocol_name", sa.String(length=100)),
        sa.Column("protocol_version", sa.String(length=100)),
        sa.Column("driver_name", sa.String(length=100)),
        sa.Column("driver_version", sa.String(length=100)),
        sa.Column("configuration_version", sa.String(length=100)),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("disabled_at", sa.DateTime()),
        sa.Column("disable_reason", sa.String(length=255)),
        sa.CheckConstraint(
            "interface_type IN "
            "('serial','usb_device','usb_storage','ethernet','file_import',"
            "'manual','proprietary','unknown')",
            name="ck_equipment_interfaces_type",
        ),
        sa.CheckConstraint(
            "direction IN ('inbound','outbound','bidirectional','unknown')",
            name="ck_equipment_interfaces_direction",
        ),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("stable_identifier"),
    )
    op.create_index(
        "ix_equipment_interfaces_equipment_id",
        "equipment_interfaces",
        ["equipment_id"],
    )

    op.create_table(
        "equipment_qualifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("equipment_interface_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default="unqualified",
            nullable=False,
        ),
        sa.Column("scope_description", sa.Text(), nullable=False),
        sa.Column("decision_reference", sa.String(length=255)),
        sa.Column("evidence_reference", sa.String(length=255)),
        sa.Column("non_clinical_comment", sa.Text()),
        sa.Column(
            "document_ids_snapshot",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("snapshot_manufacturer", sa.String(length=150)),
        sa.Column("snapshot_model", sa.String(length=150)),
        sa.Column("snapshot_device_family", sa.String(length=100)),
        sa.Column("snapshot_firmware_version", sa.String(length=100)),
        sa.Column("snapshot_interface_type", sa.String(length=30)),
        sa.Column("snapshot_protocol_name", sa.String(length=100)),
        sa.Column("snapshot_protocol_version", sa.String(length=100)),
        sa.Column("snapshot_driver_name", sa.String(length=100)),
        sa.Column("snapshot_driver_version", sa.String(length=100)),
        sa.Column("snapshot_configuration_version", sa.String(length=100)),
        sa.Column("effective_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("approved_by_user_id", sa.Integer()),
        sa.Column("approver_role", sa.String(length=30)),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("suspended_at", sa.DateTime()),
        sa.Column("suspension_reason", sa.String(length=100)),
        sa.Column("superseded_by_id", sa.Integer()),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN "
            "('unqualified','documentation_pending','technical_testing',"
            "'technically_qualified','clinical_review_pending','clinically_approved',"
            "'suspended','expired','retired')",
            name="ck_equipment_qualifications_status",
        ),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["equipment_interface_id"],
            ["equipment_interfaces.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["equipment_qualifications.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "equipment_id",
            "version",
            name="uq_equipment_qualifications_version",
        ),
        sa.UniqueConstraint("superseded_by_id"),
    )
    op.create_index(
        "ix_equipment_qualifications_equipment_id",
        "equipment_qualifications",
        ["equipment_id"],
    )
    op.create_index(
        "ix_equipment_qualifications_equipment_interface_id",
        "equipment_qualifications",
        ["equipment_interface_id"],
    )

    op.create_table(
        "equipment_approved_analytes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("qualification_id", sa.Integer(), nullable=False),
        sa.Column("analyte_code", sa.String(length=100), nullable=False),
        sa.Column("method_code", sa.String(length=100), nullable=False),
        sa.Column("sample_type", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=100), nullable=False),
        sa.Column("usage_context", sa.String(length=100)),
        sa.Column("clinical_catalog_reference", sa.String(length=255)),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("metadata_version", sa.String(length=100)),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["qualification_id"],
            ["equipment_qualifications.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "qualification_id",
            "analyte_code",
            "method_code",
            "sample_type",
            "unit",
            name="uq_equipment_approved_analytes_scope",
        ),
    )
    op.create_index(
        "ix_equipment_approved_analytes_qualification_id",
        "equipment_approved_analytes",
        ["qualification_id"],
    )

    op.create_table(
        "equipment_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("document_title", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("manufacturer", sa.String(length=150)),
        sa.Column("model", sa.String(length=150)),
        sa.Column("version", sa.String(length=100)),
        sa.Column("language", sa.String(length=50)),
        sa.Column("document_date", sa.Date()),
        sa.Column("page_count", sa.Integer()),
        sa.Column(
            "physical_copy_available",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "digital_copy_available",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("storage_reference", sa.String(length=255)),
        sa.Column(
            "contains_connectivity_section",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "contains_protocol_specification",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("review_status", sa.String(length=50)),
        sa.Column("reviewed_by_user_id", sa.Integer()),
        sa.Column("review_date", sa.Date()),
        sa.Column("checksum", sa.String(length=128)),
        sa.Column("archived_at", sa.DateTime()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_equipment_documents_equipment_id",
        "equipment_documents",
        ["equipment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_equipment_documents_equipment_id", table_name="equipment_documents")
    op.drop_table("equipment_documents")
    op.drop_index(
        "ix_equipment_approved_analytes_qualification_id",
        table_name="equipment_approved_analytes",
    )
    op.drop_table("equipment_approved_analytes")
    op.drop_index(
        "ix_equipment_qualifications_equipment_interface_id",
        table_name="equipment_qualifications",
    )
    op.drop_index(
        "ix_equipment_qualifications_equipment_id",
        table_name="equipment_qualifications",
    )
    op.drop_table("equipment_qualifications")
    op.drop_index(
        "ix_equipment_interfaces_equipment_id",
        table_name="equipment_interfaces",
    )
    op.drop_table("equipment_interfaces")
    op.drop_index("uq_equipments_asset_identifier", table_name="equipments")
    op.drop_index("ix_equipments_unit", table_name="equipments")
    with op.batch_alter_table("equipments") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("asset_identifier")
        batch_op.drop_column("lifecycle_status")
        batch_op.drop_column("clinical_use")
        batch_op.drop_column("unit")
        batch_op.drop_column("firmware_version")
        batch_op.drop_column("device_family")
        batch_op.drop_column("model")
        batch_op.drop_column("manufacturer")
