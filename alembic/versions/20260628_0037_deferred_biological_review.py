"""Ajoute la file de revue biologique différée.

Revision ID: 20260628_0037
Revises: 20260625_0036
Create Date: 2026-06-28 00:00:37
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260628_0037"
down_revision = "20260625_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("results") as batch_op:
        batch_op.add_column(
            sa.Column(
                "bio_review_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            )
        )
        batch_op.add_column(sa.Column("bio_reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("bio_reviewed_by_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_results_bio_reviewed_by_id_users",
            "users",
            ["bio_reviewed_by_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_results_bio_review_status",
            ["bio_review_status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("results") as batch_op:
        batch_op.drop_index("ix_results_bio_review_status")
        batch_op.drop_constraint(
            "fk_results_bio_reviewed_by_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("bio_reviewed_by_id")
        batch_op.drop_column("bio_reviewed_at")
        batch_op.drop_column("bio_review_status")
