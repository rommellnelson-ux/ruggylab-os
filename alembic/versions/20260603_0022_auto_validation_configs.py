"""create auto_validation_configs table

Revision ID: 20260603_0022
Revises: 20260603_0021
Create Date: 2026-06-03 00:00:22

Nouvelle table pour la configuration des règles d'auto-validation
ISO 15189 §5.8.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0022"
down_revision = "20260603_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()
    if "auto_validation_configs" not in existing_tables:
        op.create_table(
            "auto_validation_configs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(100), nullable=False, server_default="Règle par défaut"),
            sa.Column("require_all_flags_normal", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("require_no_delta", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("require_not_critical", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()
    if "auto_validation_configs" in existing_tables:
        op.drop_table("auto_validation_configs")
