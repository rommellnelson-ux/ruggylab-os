"""epidemiology indexes

Revision ID: 20260430_0009
Revises: 20260430_0008
Create Date: 2026-04-30 00:00:09
"""

from __future__ import annotations

from alembic import op

revision = "20260430_0009"
down_revision = "20260430_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_results_analysis_date",
        "results",
        ["analysis_date"],
    )
    op.create_index(
        "ix_results_is_critical_analysis_date",
        "results",
        ["is_critical", "analysis_date"],
    )
    op.create_index(
        "ix_results_equipment_analysis_date",
        "results",
        ["equipment_id", "analysis_date"],
    )
    op.create_index(
        "ix_samples_patient_id",
        "samples",
        ["patient_id"],
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_results_data_points_gin "
            "ON results USING gin (data_points)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_results_data_points_gin")
    op.drop_index("ix_samples_patient_id", table_name="samples")
    op.drop_index("ix_results_equipment_analysis_date", table_name="results")
    op.drop_index("ix_results_is_critical_analysis_date", table_name="results")
    op.drop_index("ix_results_analysis_date", table_name="results")
