"""initial schema

Revision ID: 20260428_0001
Revises:
Create Date: 2026-04-28 00:00:01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0001"
down_revision = None
branch_labels = None
depends_on = None


userrole = sa.Enum("TECHNICIAN", "OFFICER", "ADMIN", name="userrole")


def upgrade() -> None:
    userrole.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=True),
        sa.Column("role", userrole, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "equipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("last_calibration", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial_number"),
    )
    op.create_index(op.f("ix_equipments_id"), "equipments", ["id"], unique=False)

    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ipp_unique_id", sa.String(length=50), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("sex", sa.CHAR(length=1), nullable=True),
        sa.Column("rank", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ipp_unique_id"),
    )
    op.create_index(op.f("ix_patients_id"), "patients", ["id"], unique=False)
    op.create_index(op.f("ix_patients_ipp_unique_id"), "patients", ["ipp_unique_id"], unique=True)

    op.create_table(
        "samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barcode", sa.String(length=100), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("collection_date", sa.DateTime(), nullable=False),
        sa.Column("received_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("barcode"),
    )
    op.create_index(op.f("ix_samples_barcode"), "samples", ["barcode"], unique=True)
    op.create_index(op.f("ix_samples_id"), "samples", ["id"], unique=False)

    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sample_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("analysis_date", sa.DateTime(), nullable=False),
        sa.Column("data_points", sa.JSON(), nullable=False),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("validator_id", sa.Integer(), nullable=True),
        sa.Column("is_validated", sa.Boolean(), nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"]),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_results_id"), "results", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_results_id"), table_name="results")
    op.drop_table("results")
    op.drop_index(op.f("ix_samples_id"), table_name="samples")
    op.drop_index(op.f("ix_samples_barcode"), table_name="samples")
    op.drop_table("samples")
    op.drop_index(op.f("ix_patients_ipp_unique_id"), table_name="patients")
    op.drop_index(op.f("ix_patients_id"), table_name="patients")
    op.drop_table("patients")
    op.drop_index(op.f("ix_equipments_id"), table_name="equipments")
    op.drop_table("equipments")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
    userrole.drop(op.get_bind(), checkfirst=True)
