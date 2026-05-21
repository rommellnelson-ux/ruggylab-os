"""user is_active field and validator_id foreign key on results

Revision ID: 20260521_0010
Revises: 20260430_0009
Create Date: 2026-05-21 00:00:10

Changes:
- users.is_active (Boolean, NOT NULL, default True) — allows soft-deactivation
  of users without deleting audit history.
- results.validator_id now has a proper ForeignKey to users.id, enforcing
  referential integrity at the database level for medico-legal traceability.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260521_0010"
down_revision = "20260430_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Add users.is_active column (default True for existing rows)
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # 2. Add FK constraint on results.validator_id → users.id.
    #    SQLite does not support ADD CONSTRAINT after table creation, so we
    #    use batch mode (which rebuilds the table) for SQLite.
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("results") as batch_op:
            batch_op.create_foreign_key(
                "fk_results_validator_id_users",
                "users",
                ["validator_id"],
                ["id"],
            )
    else:
        op.create_foreign_key(
            "fk_results_validator_id_users",
            "results",
            "users",
            ["validator_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Remove FK constraint
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("results") as batch_op:
            batch_op.drop_constraint("fk_results_validator_id_users", type_="foreignkey")
    else:
        op.drop_constraint("fk_results_validator_id_users", "results", type_="foreignkey")

    # Remove is_active column
    op.drop_column("users", "is_active")
