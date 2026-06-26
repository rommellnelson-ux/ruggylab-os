"""Snapshots versionnes de comptes-rendus + outbox de diffusion

Revision ID: 20260622_0032
Revises: 20260622_0031
Create Date: 2026-06-22 15:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260622_0032"
down_revision = "20260622_0031"
branch_labels = None
depends_on = None


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    json_type = _json_type()

    if "report_snapshots" not in tables:
        op.create_table(
            "report_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("result_id", sa.Integer(), sa.ForeignKey("results.id"), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(20), nullable=False, server_default="final"),
            sa.Column("audience", sa.String(20), nullable=False, server_default="clinician"),
            sa.Column("schema_version", sa.String(20), nullable=False, server_default="1.0"),
            sa.Column("content_snapshot", json_type, nullable=False),
            sa.Column("pdf_sha256", sa.String(64), nullable=False),
            sa.Column("verification_token_hash", sa.String(64), nullable=False),
            sa.Column("verification_path", sa.String(255), nullable=False),
            sa.Column(
                "supersedes_snapshot_id",
                sa.Integer(),
                sa.ForeignKey("report_snapshots.id"),
                nullable=True,
            ),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("revocation_reason", sa.Text(), nullable=True),
            sa.UniqueConstraint("result_id", "version_number", name="uq_report_snapshot_version"),
            sa.UniqueConstraint("verification_token_hash", name="uq_report_snapshot_verify_token"),
        )
        op.create_index("ix_report_snapshots_result_id", "report_snapshots", ["result_id"])
        op.create_index("ix_report_snapshots_status", "report_snapshots", ["status"])

    tables = set(sa.inspect(conn).get_table_names())
    if "report_delivery_outbox" not in tables:
        op.create_table(
            "report_delivery_outbox",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "report_snapshot_id",
                sa.Integer(),
                sa.ForeignKey("report_snapshots.id"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("channel", sa.String(30), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("payload", json_type, nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("idempotency_key", name="uq_report_delivery_idempotency"),
        )
        op.create_index(
            "ix_report_delivery_outbox_snapshot",
            "report_delivery_outbox",
            ["report_snapshot_id"],
        )
        op.create_index(
            "ix_report_delivery_outbox_status",
            "report_delivery_outbox",
            ["status"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "report_delivery_outbox" in tables:
        op.drop_table("report_delivery_outbox")
    if "report_snapshots" in set(sa.inspect(conn).get_table_names()):
        op.drop_table("report_snapshots")
