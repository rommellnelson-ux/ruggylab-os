"""add controlled DHIS2 aggregate export foundation

Revision ID: 20260701_0038
Revises: 20260628_0037
"""

from alembic import op
import sqlalchemy as sa

revision = "20260701_0038"
down_revision = "20260628_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dhis2_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("internal_code", sa.String(length=50), nullable=False),
        sa.Column("data_element_uid", sa.String(length=20), nullable=False),
        sa.Column("data_set_uid", sa.String(length=20), nullable=False),
        sa.Column("org_unit_uid", sa.String(length=20), nullable=False),
        sa.Column("category_option_combo_uid", sa.String(length=20), nullable=True),
        sa.Column("period_type", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "internal_code",
            "data_set_uid",
            "org_unit_uid",
            name="uq_dhis2_mapping_scope",
        ),
    )
    op.create_index(op.f("ix_dhis2_mappings_id"), "dhis2_mappings", ["id"])
    op.create_index(
        op.f("ix_dhis2_mappings_internal_code"),
        "dhis2_mappings",
        ["internal_code"],
    )
    op.create_table(
        "dhis2_export_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("data_set_uid", sa.String(length=20), nullable=False),
        sa.Column("org_unit_uid", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("validated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["validated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "period",
            "data_set_uid",
            "org_unit_uid",
            "payload_sha256",
            name="uq_dhis2_export_idempotency",
        ),
    )
    op.create_index(op.f("ix_dhis2_export_jobs_id"), "dhis2_export_jobs", ["id"])
    op.create_index(op.f("ix_dhis2_export_jobs_period"), "dhis2_export_jobs", ["period"])
    op.create_index(
        op.f("ix_dhis2_export_jobs_payload_sha256"),
        "dhis2_export_jobs",
        ["payload_sha256"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dhis2_export_jobs_payload_sha256"), table_name="dhis2_export_jobs")
    op.drop_index(op.f("ix_dhis2_export_jobs_period"), table_name="dhis2_export_jobs")
    op.drop_index(op.f("ix_dhis2_export_jobs_id"), table_name="dhis2_export_jobs")
    op.drop_table("dhis2_export_jobs")
    op.drop_index(op.f("ix_dhis2_mappings_internal_code"), table_name="dhis2_mappings")
    op.drop_index(op.f("ix_dhis2_mappings_id"), table_name="dhis2_mappings")
    op.drop_table("dhis2_mappings")
