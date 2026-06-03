"""create equipment_maintenances table

Revision ID: 20260603_0020
Revises: 20260603_0019
Create Date: 2026-06-03 00:00:20

Nouvelle table pour la planification et le suivi de maintenance / étalonnage
des équipements de laboratoire.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0020"
down_revision = "20260603_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()
    if "equipment_maintenances" not in existing_tables:
        op.create_table(
            "equipment_maintenances",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "equipment_id",
                sa.Integer(),
                sa.ForeignKey("equipments.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("maintenance_type", sa.String(30), nullable=False, server_default="preventive"),
            sa.Column("scheduled_at", sa.DateTime(), nullable=True),
            sa.Column("performed_at", sa.DateTime(), nullable=True),
            sa.Column(
                "performed_by_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("next_due_at", sa.DateTime(), nullable=True),
            sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()
    if "equipment_maintenances" in existing_tables:
        op.drop_table("equipment_maintenances")
