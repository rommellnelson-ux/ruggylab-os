"""Aspect / qualité pré-analytique de l'échantillon (samples.aspect)

Revision ID: 20260623_0034
Revises: 20260623_0033
Create Date: 2026-06-23 00:00:34

Champ pré-analytique (hémolysé/ictérique/lipémique…) distinct du statut workflow.
Additif et idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260623_0034"
down_revision = "20260623_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "samples" in set(insp.get_table_names()):
        cols = {c["name"] for c in insp.get_columns("samples")}
        if "aspect" not in cols:
            op.add_column("samples", sa.Column("aspect", sa.String(20), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "samples" in set(insp.get_table_names()):
        cols = {c["name"] for c in insp.get_columns("samples")}
        if "aspect" in cols:
            op.drop_column("samples", "aspect")
