"""add lot_number, expiry_date, supplier to reagents (ISO 15189 traceability)

Revision ID: 20260603_0012
Revises: 20260525_0001
Create Date: 2026-06-03 00:00:12

Ajoute la traçabilité ISO 15189 sur les réactifs :
- lot_number  : numéro de lot du fabricant
- expiry_date : date de péremption (alerte automatique ≤ 30 jours)
- supplier    : fournisseur/distributeur
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0012"
down_revision = "20260525_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reagents") as batch_op:
        batch_op.add_column(sa.Column("lot_number", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("expiry_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("supplier", sa.String(200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reagents") as batch_op:
        batch_op.drop_column("supplier")
        batch_op.drop_column("expiry_date")
        batch_op.drop_column("lot_number")
