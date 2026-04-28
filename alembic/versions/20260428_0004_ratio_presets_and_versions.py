"""ratio presets and ratio versions

Revision ID: 20260428_0004
Revises: 20260428_0003
Create Date: 2026-04-28 00:00:04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0004"
down_revision = "20260428_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment_reagent_ratio_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ratio_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("reagent_id", sa.Integer(), nullable=False),
        sa.Column("consumption_per_run", sa.Float(), nullable=False),
        sa.Column("adjustment_factor", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("change_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ratio_id"], ["equipment_reagent_ratios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_equipment_reagent_ratio_versions_id"), "equipment_reagent_ratio_versions", ["id"], unique=False)

    op.create_table(
        "ratio_presets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("equipment_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_ratio_presets_id"), "ratio_presets", ["id"], unique=False)

    op.create_table(
        "ratio_preset_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("preset_id", sa.Integer(), nullable=False),
        sa.Column("reagent_name", sa.String(length=100), nullable=False),
        sa.Column("reagent_category", sa.String(length=50), nullable=True),
        sa.Column("reagent_unit", sa.String(length=20), nullable=False),
        sa.Column("consumption_per_run", sa.Float(), nullable=False),
        sa.Column("adjustment_factor", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["preset_id"], ["ratio_presets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ratio_preset_items_id"), "ratio_preset_items", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ratio_preset_items_id"), table_name="ratio_preset_items")
    op.drop_table("ratio_preset_items")
    op.drop_index(op.f("ix_ratio_presets_id"), table_name="ratio_presets")
    op.drop_table("ratio_presets")
    op.drop_index(op.f("ix_equipment_reagent_ratio_versions_id"), table_name="equipment_reagent_ratio_versions")
    op.drop_table("equipment_reagent_ratio_versions")
