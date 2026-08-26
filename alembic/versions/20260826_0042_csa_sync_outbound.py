"""Intégration CSA (flux sortant) : exam_order_items.csa_pushed_at

Revision ID: 20260826_0042
Revises: 20260826_0041
Create Date: 2026-07-10 00:00:39

Support du flux sortant RuggyLab→CSA (phase I2). Additif et idempotent :
- exam_order_items.csa_pushed_at : horodatage de remontée du résultat vers CSA
  (labo_resultats). NULL = pas encore poussé ; marqueur d'idempotence du worker.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260826_0042"
down_revision = "20260826_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "exam_order_items" in tables:
        cols = {c["name"] for c in insp.get_columns("exam_order_items")}
        if "csa_pushed_at" not in cols:
            op.add_column(
                "exam_order_items",
                sa.Column("csa_pushed_at", sa.DateTime(), nullable=True),
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "exam_order_items" in tables:
        cols = {c["name"] for c in insp.get_columns("exam_order_items")}
        if "csa_pushed_at" in cols:
            op.drop_column("exam_order_items", "csa_pushed_at")
