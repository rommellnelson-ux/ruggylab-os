"""biological_code_mappings table + bioref interpretation columns on results

Revision ID: 20260603_0028
Revises: 20260603_0027
Create Date: 2026-06-03 00:00:28

Couche d'unification des vocabulaires biologiques : table de correspondance
canonique + colonnes d'interprétation bioref complémentaires sur ``results``.
Strictement additif et idempotent.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0028"
down_revision = "20260603_0027"
branch_labels = None
depends_on = None

_RESULT_COLS = [
    ("bioref_status", sa.String(30)),
    ("bioref_comment", sa.Text()),
    ("bioref_reference_range", sa.String(120)),
    ("bioref_source", sa.String(255)),
]


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    existing_cols = {c["name"] for c in insp.get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        for name, coltype in _RESULT_COLS:
            if name not in existing_cols:
                batch_op.add_column(sa.Column(name, coltype, nullable=True))

    if "biological_code_mappings" not in insp.get_table_names():
        op.create_table(
            "biological_code_mappings",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("canonical_code", sa.String(50), nullable=False),
            sa.Column("exam_code", sa.String(50), nullable=True),
            sa.Column("test_code", sa.String(50), nullable=True),
            sa.Column("analyte_code", sa.String(50), nullable=True),
            sa.Column("component_of", sa.String(50), nullable=True),
            sa.Column("label", sa.String(150), nullable=True),
            sa.Column("category", sa.String(100), nullable=True),
            sa.Column("specimen_type", sa.String(100), nullable=True),
            sa.Column("unit", sa.String(50), nullable=True),
            sa.Column("is_panel", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for col in ("canonical_code", "exam_code", "test_code", "analyte_code", "component_of"):
            op.create_index(
                f"ix_biological_code_mappings_{col}", "biological_code_mappings", [col]
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "biological_code_mappings" in insp.get_table_names():
        for col in ("canonical_code", "exam_code", "test_code", "analyte_code", "component_of"):
            op.drop_index(
                f"ix_biological_code_mappings_{col}", table_name="biological_code_mappings"
            )
        op.drop_table("biological_code_mappings")

    existing_cols = {c["name"] for c in insp.get_columns("results")}
    with op.batch_alter_table("results") as batch_op:
        for name, _ in reversed(_RESULT_COLS):
            if name in existing_cols:
                batch_op.drop_column(name)
