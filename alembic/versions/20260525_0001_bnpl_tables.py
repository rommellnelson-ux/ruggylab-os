"""add bnpl_schedules and bnpl_payments tables

Revision ID: 20260525_0001
Revises: 20260521_0011
Create Date: 2026-05-25 00:00:01

Ajoute les tables de suivi des échéances BNPL (Buy Now Pay Later / micro-crédit santé CMU).
Compatible SQLite et PostgreSQL.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260525_0001"
down_revision = "20260521_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bnpl_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_ref", sa.String(length=200), nullable=False),
        sa.Column("prescriber_id", sa.String(length=200), nullable=True),
        sa.Column("total_amount_xof", sa.Integer(), nullable=False),
        sa.Column("installment_months", sa.Integer(), nullable=False),
        sa.Column("monthly_amount_xof", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bnpl_schedules_id"), "bnpl_schedules", ["id"])
    op.create_index(op.f("ix_bnpl_schedules_patient_ref"), "bnpl_schedules", ["patient_ref"])

    op.create_table(
        "bnpl_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("installment_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("amount_xof", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["bnpl_schedules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bnpl_payments_id"), "bnpl_payments", ["id"])
    op.create_index(op.f("ix_bnpl_payments_schedule_id"), "bnpl_payments", ["schedule_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bnpl_payments_schedule_id"), table_name="bnpl_payments")
    op.drop_index(op.f("ix_bnpl_payments_id"), table_name="bnpl_payments")
    op.drop_table("bnpl_payments")

    op.drop_index(op.f("ix_bnpl_schedules_patient_ref"), table_name="bnpl_schedules")
    op.drop_index(op.f("ix_bnpl_schedules_id"), table_name="bnpl_schedules")
    op.drop_table("bnpl_schedules")
