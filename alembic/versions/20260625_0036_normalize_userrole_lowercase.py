"""Normalise users.role en minuscules (alignement StrEnum / type PG userrole)

Revision ID: 20260625_0036
Revises: 20260623_0035
Create Date: 2026-06-25 00:00:36

Le modèle utilisait ``Enum(UserRole)`` sans ``values_callable`` : SQLAlchemy
stockait alors les NOMS des membres (majuscules : 'ADMIN', 'TECHNICIAN'…),
alors que le StrEnum ``UserRole`` et le type PostgreSQL ``userrole`` déclarent
des VALEURS en minuscules ('admin', 'technician'…). Conséquence : toute écriture
de ``users.role`` échouait sur PostgreSQL ("invalid input value for enum"),
tandis que SQLite (colonne TEXT libre) accumulait des majuscules.

Le modèle est désormais corrigé (``values_callable``). Cette migration normalise
les données héritées :

- SQLite (et dialectes à colonne libre) : ``UPDATE users SET role = lower(role)``.
- PostgreSQL : aucune donnée majuscule ne peut exister (les écritures
  échouaient) ; l'UPDATE est un no-op sûr, conservé par symétrie/robustesse.

Strictement additif côté schéma (pas de DDL).
"""

from __future__ import annotations

from alembic import op

revision = "20260625_0036"
down_revision = "20260623_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Le cast text est requis pour repasser une valeur de l'enum par lower().
        op.execute("UPDATE users SET role = lower(role::text)::userrole")
    else:
        op.execute("UPDATE users SET role = lower(role)")


def downgrade() -> None:
    # Pas de retour arrière : la casse majuscule était un bug, pas un état cible.
    pass
