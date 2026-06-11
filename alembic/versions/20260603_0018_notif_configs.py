"""create notif_configs table

Revision ID: 20260603_0018
Revises: 20260603_0017
Create Date: 2026-06-03 00:00:18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0018"
down_revision = "20260603_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "notif_configs" not in existing:
        op.create_table(
            "notif_configs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("webhook_url", sa.String(500), nullable=True),
            sa.Column("email", sa.String(200), nullable=True),
            sa.Column("delay_minutes", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "notif_configs" in existing:
        op.drop_table("notif_configs")
