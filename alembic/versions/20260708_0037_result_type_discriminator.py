"""Discriminateur de nature du résultat (results.result_type) — Flux 3

Revision ID: 20260708_0037
Revises: 20260625_0036
Create Date: 2026-07-08 00:00:37

Distingue les résultats qualitatifs/textuels (parasitologie, cytologie, frottis)
des résultats chiffrés, sans dépendre des clés du JSONB data_points. Additif,
idempotent, nullable (l'historique reste NULL). Indexé pour filtrer par nature.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260708_0037"
down_revision = "20260625_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "results" in set(insp.get_table_names()):
        cols = {c["name"] for c in insp.get_columns("results")}
        if "result_type" not in cols:
            op.add_column("results", sa.Column("result_type", sa.String(30), nullable=True))
            op.create_index("ix_results_result_type", "results", ["result_type"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "results" in set(insp.get_table_names()):
        indexes = {ix["name"] for ix in insp.get_indexes("results")}
        if "ix_results_result_type" in indexes:
            op.drop_index("ix_results_result_type", table_name="results")
        cols = {c["name"] for c in insp.get_columns("results")}
        if "result_type" in cols:
            op.drop_column("results", "result_type")
