"""Tarifs d'examens (exam_tariffs) + lien plan de paiement sur les factures

Revision ID: 20260622_0031
Revises: 20260618_0030
Create Date: 2026-06-22 00:00:31

Deux ajouts additifs et idempotents pour boucler le cycle facturation :
  - exam_tariffs : prix unitaire (FCFA) par examen, pour générer
    automatiquement les lignes de facture depuis une prescription terminée ;
  - invoices.payment_plan_id : référence optionnelle vers un plan BNPL, créé
    uniquement quand le patient ne peut pas régler le reste à charge comptant.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260622_0031"
down_revision = "20260618_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "exam_tariffs" not in tables:
        op.create_table(
            "exam_tariffs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("exam_code", sa.String(50), nullable=False),
            sa.Column("label", sa.String(150), nullable=False),
            sa.Column("price_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_exam_tariffs_exam_code", "exam_tariffs", ["exam_code"], unique=True)

    if "invoices" in tables:
        cols = {c["name"] for c in insp.get_columns("invoices")}
        if "payment_plan_id" not in cols:
            op.add_column("invoices", sa.Column("payment_plan_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "invoices" in tables:
        cols = {c["name"] for c in insp.get_columns("invoices")}
        if "payment_plan_id" in cols:
            op.drop_column("invoices", "payment_plan_id")
    if "exam_tariffs" in set(insp.get_table_names()):
        op.drop_table("exam_tariffs")
