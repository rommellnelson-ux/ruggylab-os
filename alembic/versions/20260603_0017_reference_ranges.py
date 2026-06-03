"""create reference_ranges table

Revision ID: 20260603_0017
Revises: 20260603_0016
Create Date: 2026-06-03 00:00:17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0017"
down_revision = "20260603_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "reference_ranges" not in existing:
        op.create_table(
            "reference_ranges",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("analyte", sa.String(50), nullable=False),
            sa.Column("sex", sa.String(1), nullable=False, server_default="*"),
            sa.Column("age_min_years", sa.Float(), nullable=True),
            sa.Column("age_max_years", sa.Float(), nullable=True),
            sa.Column("low_normal", sa.Float(), nullable=True),
            sa.Column("high_normal", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(30), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "reference_ranges" in existing:
        op.drop_table("reference_ranges")
