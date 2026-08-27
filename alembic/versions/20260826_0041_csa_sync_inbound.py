"""Intégration CSA (flux entrant) : csa_prescription_id, birth_date_estimee, csa_sync_state

Revision ID: 20260826_0041
Revises: 20260724_0039
Create Date: 2026-07-09 00:00:38

Support du flux entrant CSA→RuggyLab (phase I1). Additif et idempotent :
- exam_orders.csa_prescription_id : idempotence de l'intégration (unique).
- patients.birth_date_estimee : DDN sentinelle quand la source (CSA) n'en a pas.
- csa_sync_state : watermark du worker de poll (une seule ligne).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260826_0041"
down_revision = "20260724_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "exam_orders" in tables:
        cols = {c["name"] for c in insp.get_columns("exam_orders")}
        if "csa_prescription_id" not in cols:
            op.add_column(
                "exam_orders",
                sa.Column("csa_prescription_id", sa.String(80), nullable=True),
            )
            op.create_index(
                "ix_exam_orders_csa_prescription_id",
                "exam_orders",
                ["csa_prescription_id"],
                unique=True,
            )

    if "patients" in tables:
        cols = {c["name"] for c in insp.get_columns("patients")}
        if "birth_date_estimee" not in cols:
            op.add_column(
                "patients",
                sa.Column(
                    "birth_date_estimee",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )

    if "csa_sync_state" not in tables:
        op.create_table(
            "csa_sync_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("last_pulled_at", sa.String(40), nullable=True),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "csa_sync_state" in tables:
        op.drop_table("csa_sync_state")

    if "patients" in tables:
        cols = {c["name"] for c in insp.get_columns("patients")}
        if "birth_date_estimee" in cols:
            op.drop_column("patients", "birth_date_estimee")

    if "exam_orders" in tables:
        indexes = {ix["name"] for ix in insp.get_indexes("exam_orders")}
        if "ix_exam_orders_csa_prescription_id" in indexes:
            op.drop_index("ix_exam_orders_csa_prescription_id", table_name="exam_orders")
        cols = {c["name"] for c in insp.get_columns("exam_orders")}
        if "csa_prescription_id" in cols:
            op.drop_column("exam_orders", "csa_prescription_id")
