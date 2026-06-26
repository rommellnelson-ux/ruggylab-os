"""create revoked_tokens table (access-token denylist)

Revision ID: 20260603_0023
Revises: 20260603_0022
Create Date: 2026-06-03 00:00:23

Liste de révocation des jetons d'accès JWT par ``jti``. Permet d'invalider
un jeton d'accès avant son expiration (déconnexion, compromission).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0023"
down_revision = "20260603_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()
    if "revoked_tokens" not in existing_tables:
        op.create_table(
            "revoked_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("jti", sa.String(64), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()
    if "revoked_tokens" in existing_tables:
        op.drop_index("ix_revoked_tokens_jti", table_name="revoked_tokens")
        op.drop_table("revoked_tokens")
