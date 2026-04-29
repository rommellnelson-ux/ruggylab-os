"""stock movements

Revision ID: 20260429_0005
Revises: 20260428_0004
Create Date: 2026-04-29 00:00:05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260429_0005"
down_revision = "20260428_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reagent_id", sa.Integer(), nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("quantity_delta", sa.Float(), nullable=False),
        sa.Column("stock_before", sa.Float(), nullable=False),
        sa.Column("stock_after", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["reagent_id"], ["reagents.id"]),
        sa.ForeignKeyConstraint(["result_id"], ["results.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_movements_id"), "stock_movements", ["id"])
    op.create_index(
        op.f("ix_stock_movements_reagent_id"),
        "stock_movements",
        ["reagent_id"],
    )
    op.create_index(
        op.f("ix_stock_movements_result_id"),
        "stock_movements",
        ["result_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_movements_result_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_reagent_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_id"), table_name="stock_movements")
    op.drop_table("stock_movements")
