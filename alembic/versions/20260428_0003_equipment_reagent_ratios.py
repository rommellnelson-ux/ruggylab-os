"""equipment reagent ratios

Revision ID: 20260428_0003
Revises: 20260428_0002
Create Date: 2026-04-28 00:00:03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0003"
down_revision = "20260428_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment_reagent_ratios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("reagent_id", sa.Integer(), nullable=False),
        sa.Column("consumption_per_run", sa.Float(), nullable=False),
        sa.Column("adjustment_factor", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"]),
        sa.ForeignKeyConstraint(["reagent_id"], ["reagents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipment_id", "reagent_id", name="uq_equipment_reagent_ratio_pair"),
    )
    op.create_index(op.f("ix_equipment_reagent_ratios_id"), "equipment_reagent_ratios", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_equipment_reagent_ratios_id"), table_name="equipment_reagent_ratios")
    op.drop_table("equipment_reagent_ratios")
