"""create non_conformities and corrective_actions tables (QMS NC/CAPA)

Revision ID: 20260603_0025
Revises: 20260603_0024
Create Date: 2026-06-03 00:00:25

Module qualité ISO 15189 §4.9/§4.10 : déclaration des non-conformités et
actions correctives / préventives associées.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0025"
down_revision = "20260603_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()

    if "non_conformities" not in existing:
        op.create_table(
            "non_conformities",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
            sa.Column("severity", sa.String(20), nullable=False, server_default="minor"),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("linked_entity_type", sa.String(50), nullable=True),
            sa.Column("linked_entity_id", sa.String(50), nullable=True),
            sa.Column("detected_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("detected_at", sa.DateTime(), nullable=False),
            sa.Column("due_date", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("root_cause", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_non_conformities_status", "non_conformities", ["status"])

    if "corrective_actions" not in existing:
        op.create_table(
            "corrective_actions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "non_conformity_id",
                sa.Integer(),
                sa.ForeignKey("non_conformities.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("action_type", sa.String(20), nullable=False, server_default="corrective"),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("responsible_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("due_date", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
            sa.Column(
                "effectiveness_checked", sa.Boolean(), nullable=False, server_default="0"
            ),
            sa.Column("effectiveness_notes", sa.Text(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = sa.inspect(conn).get_table_names()
    if "corrective_actions" in existing:
        op.drop_table("corrective_actions")
    if "non_conformities" in existing:
        if "ix_non_conformities_status" in {
            i["name"] for i in sa.inspect(conn).get_indexes("non_conformities")
        }:
            op.drop_index("ix_non_conformities_status", table_name="non_conformities")
        op.drop_table("non_conformities")
