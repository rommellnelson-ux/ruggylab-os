"""add delta_exceeded, delta_analytes, flags to results

Revision ID: 20260603_0019
Revises: 20260603_0018
Create Date: 2026-06-03 00:00:19

Nouvelles colonnes sur la table results :
- delta_exceeded    : bool, True si variation inter-résultats > seuil
- delta_analytes    : JSON, dict analyte → variation observée
- flags             : JSON, dict analyte → flag HH/H/N/L/LL
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0019"
down_revision = "20260603_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = {col["name"] for col in sa.inspect(conn).get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        if "delta_exceeded" not in existing_cols:
            batch_op.add_column(
                sa.Column("delta_exceeded", sa.Boolean(), nullable=False, server_default="0")
            )
        if "delta_analytes" not in existing_cols:
            batch_op.add_column(sa.Column("delta_analytes", sa.JSON(), nullable=True))
        if "flags" not in existing_cols:
            batch_op.add_column(sa.Column("flags", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    existing_cols = {col["name"] for col in sa.inspect(conn).get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        if "flags" in existing_cols:
            batch_op.drop_column("flags")
        if "delta_analytes" in existing_cols:
            batch_op.drop_column("delta_analytes")
        if "delta_exceeded" in existing_cols:
            batch_op.drop_column("delta_exceeded")
