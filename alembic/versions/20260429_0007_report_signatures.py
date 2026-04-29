"""report signatures

Revision ID: 20260429_0007
Revises: 20260429_0006
Create Date: 2026-04-29 00:00:07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260429_0007"
down_revision = "20260429_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_signatures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=False),
        sa.Column("signed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_meaning", sa.String(length=150), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["result_id"], ["results.id"]),
        sa.ForeignKeyConstraint(["signed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_id", name="uq_report_signatures_result_id"),
    )
    op.create_index(op.f("ix_report_signatures_id"), "report_signatures", ["id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_report_signatures_id"), table_name="report_signatures")
    op.drop_table("report_signatures")
