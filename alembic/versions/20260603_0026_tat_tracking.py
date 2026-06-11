"""TAT tracking: phase timestamps on results + tat_targets table

Revision ID: 20260603_0026
Revises: 20260603_0025
Create Date: 2026-06-03 00:00:26

Suivi du Turnaround Time : horodatages de phases (optionnels) sur ``results``
et table ``tat_targets`` (délai cible par examen). Migration idempotente.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0026"
down_revision = "20260603_0025"
branch_labels = None
depends_on = None

_RESULT_COLUMNS = [
    ("exam_code", sa.String(50)),
    ("prescribed_at", sa.DateTime()),
    ("registered_at", sa.DateTime()),
    ("collected_at", sa.DateTime()),
    ("received_at", sa.DateTime()),
    ("analysis_started_at", sa.DateTime()),
    ("analysis_finished_at", sa.DateTime()),
    ("tech_validated_at", sa.DateTime()),
    ("bio_validated_at", sa.DateTime()),
    ("released_at", sa.DateTime()),
]


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    existing_cols = {c["name"] for c in insp.get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        for name, coltype in _RESULT_COLUMNS:
            if name not in existing_cols:
                batch_op.add_column(sa.Column(name, coltype, nullable=True))

    if "tat_targets" not in insp.get_table_names():
        op.create_table(
            "tat_targets",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("exam_code", sa.String(50), nullable=False),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("target_minutes", sa.Integer(), nullable=False),
            sa.Column("warn_factor", sa.Float(), nullable=False, server_default="1.5"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_tat_targets_exam_code", "tat_targets", ["exam_code"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "tat_targets" in insp.get_table_names():
        op.drop_index("ix_tat_targets_exam_code", table_name="tat_targets")
        op.drop_table("tat_targets")

    existing_cols = {c["name"] for c in insp.get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        for name, _ in reversed(_RESULT_COLUMNS):
            if name in existing_cols:
                batch_op.drop_column(name)
