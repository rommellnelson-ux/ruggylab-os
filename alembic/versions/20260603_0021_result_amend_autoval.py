"""add is_auto_validated, auto_validated_at, amendment_reason to results

Revision ID: 20260603_0021
Revises: 20260603_0020
Create Date: 2026-06-03 00:00:21

Nouvelles colonnes sur la table results :
- is_auto_validated   : bool, True si validé automatiquement par la règle ISO 15189 §5.8
- auto_validated_at   : datetime, horodatage de l'auto-validation
- amendment_reason    : str(500), motif de la dernière correction de données
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0021"
down_revision = "20260603_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = {col["name"] for col in sa.inspect(conn).get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        if "is_auto_validated" not in existing_cols:
            batch_op.add_column(
                sa.Column("is_auto_validated", sa.Boolean(), nullable=False, server_default="0")
            )
        if "auto_validated_at" not in existing_cols:
            batch_op.add_column(sa.Column("auto_validated_at", sa.DateTime(), nullable=True))
        if "amendment_reason" not in existing_cols:
            batch_op.add_column(sa.Column("amendment_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    existing_cols = {col["name"] for col in sa.inspect(conn).get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        if "amendment_reason" in existing_cols:
            batch_op.drop_column("amendment_reason")
        if "auto_validated_at" in existing_cols:
            batch_op.drop_column("auto_validated_at")
        if "is_auto_validated" in existing_cols:
            batch_op.drop_column("is_auto_validated")
