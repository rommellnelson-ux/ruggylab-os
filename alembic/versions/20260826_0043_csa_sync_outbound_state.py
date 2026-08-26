"""Intégration CSA (durcissement I4) : état du flux sortant dans csa_sync_state

Revision ID: 20260826_0043
Revises: 20260826_0042
Create Date: 2026-07-11 00:00:40

Observabilité du worker sortant (phase I4). Additif et idempotent :
- csa_sync_state.last_outbound_run_at : dernier cycle sortant.
- csa_sync_state.last_outbound_error  : dernière erreur sortante (NULL si OK).
- csa_sync_state.pushed_count         : total de résultats remontés vers CSA.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260826_0043"
down_revision = "20260826_0042"
branch_labels = None
depends_on = None

_COLS = {
    "last_outbound_run_at": lambda: sa.Column("last_outbound_run_at", sa.DateTime(), nullable=True),
    "last_outbound_error": lambda: sa.Column("last_outbound_error", sa.Text(), nullable=True),
    "pushed_count": lambda: sa.Column("pushed_count", sa.Integer(), nullable=False, server_default="0"),
}


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "csa_sync_state" not in set(insp.get_table_names()):
        return
    existing = {c["name"] for c in insp.get_columns("csa_sync_state")}
    for name, factory in _COLS.items():
        if name not in existing:
            op.add_column("csa_sync_state", factory())


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "csa_sync_state" not in set(insp.get_table_names()):
        return
    existing = {c["name"] for c in insp.get_columns("csa_sync_state")}
    for name in _COLS:
        if name in existing:
            op.drop_column("csa_sync_state", name)
