"""dh36 inbound messages

Revision ID: 20260429_0006
Revises: 20260429_0005
Create Date: 2026-04-29 00:00:06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260429_0006"
down_revision = "20260429_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dh36_inbound_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("message_control_id", sa.String(length=100), nullable=True),
        sa.Column("sample_barcode", sa.String(length=100), nullable=True),
        sa.Column("equipment_serial", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("raw_message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["result_id"], ["results.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_control_id",
            name="uq_dh36_inbound_messages_message_control_id",
        ),
        sa.UniqueConstraint("raw_hash", name="uq_dh36_inbound_messages_raw_hash"),
    )
    op.create_index(
        op.f("ix_dh36_inbound_messages_equipment_serial"),
        "dh36_inbound_messages",
        ["equipment_serial"],
    )
    op.create_index(
        op.f("ix_dh36_inbound_messages_id"), "dh36_inbound_messages", ["id"]
    )
    op.create_index(
        op.f("ix_dh36_inbound_messages_message_control_id"),
        "dh36_inbound_messages",
        ["message_control_id"],
    )
    op.create_index(
        op.f("ix_dh36_inbound_messages_raw_hash"),
        "dh36_inbound_messages",
        ["raw_hash"],
    )
    op.create_index(
        op.f("ix_dh36_inbound_messages_sample_barcode"),
        "dh36_inbound_messages",
        ["sample_barcode"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_dh36_inbound_messages_sample_barcode"),
        table_name="dh36_inbound_messages",
    )
    op.drop_index(
        op.f("ix_dh36_inbound_messages_raw_hash"),
        table_name="dh36_inbound_messages",
    )
    op.drop_index(
        op.f("ix_dh36_inbound_messages_message_control_id"),
        table_name="dh36_inbound_messages",
    )
    op.drop_index(
        op.f("ix_dh36_inbound_messages_id"), table_name="dh36_inbound_messages"
    )
    op.drop_index(
        op.f("ix_dh36_inbound_messages_equipment_serial"),
        table_name="dh36_inbound_messages",
    )
    op.drop_table("dh36_inbound_messages")
