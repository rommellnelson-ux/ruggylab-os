"""add qc_controls and qc_results tables (Westgard / Levey-Jennings)

Revision ID: 20260603_0013
Revises: 20260603_0012
Create Date: 2026-06-03 00:00:13

Crée les tables pour le contrôle qualité analytique ISO 15189 :
- qc_controls : matériau de contrôle (analyte, niveau, moyenne cible, SD)
- qc_results  : mesures quotidiennes + règles Westgard violées (JSON)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0013"
down_revision = "20260603_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard against create_all() having already created these tables at startup
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()

    if "qc_controls" not in existing:
        op.create_table(
            "qc_controls",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("analyte", sa.String(100), nullable=False),
            sa.Column("level", sa.String(50), nullable=False, server_default="Niveau 1"),
            sa.Column("unit", sa.String(30), nullable=False, server_default=""),
            sa.Column("target_mean", sa.Float(), nullable=False),
            sa.Column("target_sd", sa.Float(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_qc_controls_id"), "qc_controls", ["id"])

    if "qc_results" not in existing:
        op.create_table(
            "qc_results",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("control_id", sa.Integer(), nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("measured_at", sa.Date(), nullable=False),
            sa.Column("operator", sa.String(100), nullable=True),
            sa.Column("violations", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["control_id"], ["qc_controls.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_qc_results_id"), "qc_results", ["id"])
        op.create_index(op.f("ix_qc_results_control_id"), "qc_results", ["control_id"])
        op.create_index(op.f("ix_qc_results_measured_at"), "qc_results", ["measured_at"])


def downgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "qc_results" in existing:
        op.drop_index(op.f("ix_qc_results_measured_at"), table_name="qc_results")
        op.drop_index(op.f("ix_qc_results_control_id"), table_name="qc_results")
        op.drop_index(op.f("ix_qc_results_id"), table_name="qc_results")
        op.drop_table("qc_results")
    if "qc_controls" in existing:
        op.drop_index(op.f("ix_qc_controls_id"), table_name="qc_controls")
        op.drop_table("qc_controls")
