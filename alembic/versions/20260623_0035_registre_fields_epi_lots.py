"""Compléments registre : n° labo, préleveur, téléphone, quartier, service ;
notifications épidémiologiques (MADO) ; lots de réactifs (FEFO).

Revision ID: 20260623_0035
Revises: 20260623_0034
Create Date: 2026-06-23 00:00:35

Additif et idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260623_0035"
down_revision = "20260623_0034"
branch_labels = None
depends_on = None

_COLUMNS = {
    "patients": [
        ("phone", sa.String(30)),
        ("residence_quarter", sa.String(150)),
    ],
    "samples": [
        ("lab_number", sa.String(20)),
        ("collected_by_label", sa.String(150)),
    ],
    "exam_orders": [
        ("requesting_service", sa.String(100)),
    ],
}


def _add_missing_columns(insp) -> None:
    tables = set(insp.get_table_names())
    for table, cols in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for name, col_type in cols:
            if name not in existing:
                op.add_column(table, sa.Column(name, col_type, nullable=True))


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    _add_missing_columns(insp)
    tables = set(insp.get_table_names())

    if "epi_notifications" not in tables:
        op.create_table(
            "epi_notifications",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
            sa.Column("patient_label", sa.String(150), nullable=True),
            sa.Column("residence_quarter", sa.String(150), nullable=True),
            sa.Column("pathology", sa.String(150), nullable=False),
            sa.Column("sample_barcode", sa.String(100), nullable=True),
            sa.Column("detected_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="to_send"),
            sa.Column("notified_at", sa.DateTime(), nullable=True),
            sa.Column("channel", sa.String(100), nullable=True),
            sa.Column("declared_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_epi_notifications_status", "epi_notifications", ["status"])

    if "reagent_lots" not in tables:
        op.create_table(
            "reagent_lots",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("reagent_id", sa.Integer(), sa.ForeignKey("reagents.id"), nullable=False),
            sa.Column("lot_number", sa.String(100), nullable=False),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        )
        op.create_index("ix_reagent_lots_reagent_id", "reagent_lots", ["reagent_id"])
        op.create_index("ix_reagent_lots_status", "reagent_lots", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "reagent_lots" in tables:
        op.drop_table("reagent_lots")
    if "epi_notifications" in tables:
        op.drop_table("epi_notifications")
    for table, cols in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for name, _ in cols:
            if name in existing:
                op.drop_column(table, name)
