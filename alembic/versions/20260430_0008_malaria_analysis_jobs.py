"""malaria analysis jobs

Revision ID: 20260430_0008
Revises: 20260429_0007
Create Date: 2026-04-30 00:00:08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260430_0008"
down_revision = "20260429_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "malaria_analysis_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("image_url", sa.String(length=255), nullable=False),
        sa.Column("prediction_label", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["result_id"], ["results.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_malaria_analysis_jobs_id"), "malaria_analysis_jobs", ["id"]
    )
    op.create_index(
        op.f("ix_malaria_analysis_jobs_result_id"),
        "malaria_analysis_jobs",
        ["result_id"],
    )
    op.create_index(
        op.f("ix_malaria_analysis_jobs_status"),
        "malaria_analysis_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_malaria_analysis_jobs_status"), table_name="malaria_analysis_jobs"
    )
    op.drop_index(
        op.f("ix_malaria_analysis_jobs_result_id"),
        table_name="malaria_analysis_jobs",
    )
    op.drop_index(
        op.f("ix_malaria_analysis_jobs_id"), table_name="malaria_analysis_jobs"
    )
    op.drop_table("malaria_analysis_jobs")
