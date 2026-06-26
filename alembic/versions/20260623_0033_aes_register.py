"""Registre des Accidents d'Exposition au Sang (AES)

Revision ID: 20260623_0033
Revises: 20260622_0032
Create Date: 2026-06-23 00:00:33

Table de traçabilité des AES (sécurité du personnel). Additive et idempotente.

NB : re-parentée sur 0032 (report snapshots, désormais committé) pour garder une
chaîne de migrations strictement linéaire.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260623_0033"
down_revision = "20260622_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "aes_incidents" in set(insp.get_table_names()):
        return
    op.create_table(
        "aes_incidents",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("agent_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("agent_label", sa.String(150), nullable=True),
        sa.Column("declared_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("location", sa.String(150), nullable=True),
        sa.Column("exposure_type", sa.String(40), nullable=False, server_default="piqure"),
        sa.Column("circumstances", sa.Text(), nullable=False),
        sa.Column("immediate_measures", sa.Text(), nullable=True),
        sa.Column("source_label", sa.String(150), nullable=True),
        sa.Column("source_serology", sa.String(120), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="declared"),
        sa.Column("followup_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_aes_incidents_status", "aes_incidents", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "aes_incidents" in set(insp.get_table_names()):
        op.drop_table("aes_incidents")
