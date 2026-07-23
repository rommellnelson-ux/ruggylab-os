"""Version de sécurité des sessions utilisateur.

Revision ID: 20260723_0038
Revises: 20260708_0037
Create Date: 2026-07-23 00:00:38
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260723_0038"
down_revision = "20260708_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "auth_version")
