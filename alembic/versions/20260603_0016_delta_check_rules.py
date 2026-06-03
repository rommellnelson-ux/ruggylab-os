"""create delta_check_rules table

Revision ID: 20260603_0016
Revises: 20260603_0015
Create Date: 2026-06-03 00:00:16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0016"
down_revision = "20260603_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "delta_check_rules" not in existing:
        op.create_table(
            "delta_check_rules",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("analyte", sa.String(50), nullable=False, unique=True),
            sa.Column("delta_pct", sa.Float(), nullable=True),
            sa.Column("delta_abs", sa.Float(), nullable=True),
            sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("unit", sa.String(30), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "delta_check_rules" in existing:
        op.drop_table("delta_check_rules")
