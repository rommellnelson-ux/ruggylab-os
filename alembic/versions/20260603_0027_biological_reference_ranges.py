"""create biological_reference_ranges table

Revision ID: 20260603_0027
Revises: 20260603_0026
Create Date: 2026-06-03 00:00:27

Référentiel de valeurs biologiques de référence (IFCC/Tietz/OMS…), stratifié
par sexe et âge, avec seuils critiques et interprétation. Migration idempotente.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0027"
down_revision = "20260603_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if "biological_reference_ranges" not in sa.inspect(conn).get_table_names():
        op.create_table(
            "biological_reference_ranges",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("test_code", sa.String(50), nullable=False),
            sa.Column("test_name", sa.String(255), nullable=False),
            sa.Column("category", sa.String(100), nullable=True),
            sa.Column("specimen", sa.String(100), nullable=True),
            sa.Column("sex", sa.String(20), nullable=False, server_default="ALL"),
            sa.Column("age_min_years", sa.Float(), nullable=False, server_default="0"),
            sa.Column("age_max_years", sa.Float(), nullable=False, server_default="120"),
            sa.Column("lower_limit", sa.Float(), nullable=True),
            sa.Column("upper_limit", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(50), nullable=True),
            sa.Column("normal_text", sa.String(255), nullable=True),
            sa.Column("critical_low", sa.Float(), nullable=True),
            sa.Column("critical_high", sa.Float(), nullable=True),
            sa.Column("interpretation", sa.Text(), nullable=True),
            sa.Column("source", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        )
        op.create_index(
            "ix_biological_reference_ranges_test_code",
            "biological_reference_ranges",
            ["test_code"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if "biological_reference_ranges" in sa.inspect(conn).get_table_names():
        op.drop_index(
            "ix_biological_reference_ranges_test_code",
            table_name="biological_reference_ranges",
        )
        op.drop_table("biological_reference_ranges")
