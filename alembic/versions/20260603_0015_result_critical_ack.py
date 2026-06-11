"""add critical_ack_at and critical_ack_by_id to results

Revision ID: 20260603_0015
Revises: 20260603_0014
Create Date: 2026-06-03 00:00:15

Traçabilité d'acquittement des valeurs critiques (panic values) :
- critical_ack_at      : horodatage UTC de l'acquittement
- critical_ack_by_id   : FK vers l'utilisateur ayant acquitté
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0015"
down_revision = "20260603_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("results") as batch_op:
        batch_op.add_column(sa.Column("critical_ack_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("critical_ack_by_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("results") as batch_op:
        batch_op.drop_column("critical_ack_by_id")
        batch_op.drop_column("critical_ack_at")
