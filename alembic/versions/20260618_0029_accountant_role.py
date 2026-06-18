"""Ajoute la valeur 'accountant' à l'enum userrole (rôle comptable / gestion)

Revision ID: 20260618_0029
Revises: 20260603_0028
Create Date: 2026-06-18 00:00:29

Rôle comptable : accès cloisonné à la facturation/paiements, sans données
cliniques. Strictement additif et idempotent.

- PostgreSQL : ``ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'accountant'``
  (hors transaction via autocommit_block, requis par PostgreSQL).
- SQLite : l'enum est stocké en TEXT sans contrainte → aucun DDL nécessaire.
"""

from __future__ import annotations

from alembic import op

revision = "20260618_0029"
down_revision = "20260603_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'accountant'")
    # SQLite : aucune action (enum = TEXT libre).


def downgrade() -> None:
    # PostgreSQL ne permet pas de retirer proprement une valeur d'enum sans
    # recréer le type ; on laisse la valeur en place (sans impact fonctionnel).
    pass
