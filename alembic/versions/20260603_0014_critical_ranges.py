"""add critical_ranges table (panic values — ISO 15189)

Revision ID: 20260603_0014
Revises: 20260603_0013
Create Date: 2026-06-03 00:00:14

Seuils critiques (panic values) configurables par analyte.
Quand un résultat contient une valeur hors seuil, is_critical est
automatiquement positionné à True par le service critical_checker.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0014"
down_revision = "20260603_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()

    if "critical_ranges" not in existing:
        op.create_table(
            "critical_ranges",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("analyte", sa.String(50), nullable=False),
            sa.Column("low_critical", sa.Float(), nullable=True),
            sa.Column("high_critical", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(30), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_critical_ranges_id"), "critical_ranges", ["id"])
        op.create_index(
            op.f("ix_critical_ranges_analyte"), "critical_ranges", ["analyte"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "critical_ranges" in existing:
        op.drop_index(op.f("ix_critical_ranges_analyte"), table_name="critical_ranges")
        op.drop_index(op.f("ix_critical_ranges_id"), table_name="critical_ranges")
        op.drop_table("critical_ranges")
