"""add unit column to users and patients (RBAC scoping)

Revision ID: 20260603_0024
Revises: 20260603_0023
Create Date: 2026-06-03 00:00:24

Colonne ``unit`` (unité / service de rattachement) sur ``users`` et
``patients`` pour le cloisonnement RBAC des dossiers patient.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0024"
down_revision = "20260603_0023"
branch_labels = None
depends_on = None


def _has_column(conn, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn, "users", "unit"):
        op.add_column("users", sa.Column("unit", sa.String(100), nullable=True))
    if not _has_column(conn, "patients", "unit"):
        op.add_column("patients", sa.Column("unit", sa.String(100), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _has_column(conn, "patients", "unit"):
        op.drop_column("patients", "unit")
    if _has_column(conn, "users", "unit"):
        op.drop_column("users", "unit")
