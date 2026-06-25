"""Régression : cohérence de l'enum userrole entre le code, l'API et PostgreSQL.

Le modèle stockait autrefois les NOMS des membres (majuscules : 'ADMIN') au lieu
des VALEURS du StrEnum (minuscules : 'admin'). Le type PostgreSQL ``userrole``
n'acceptant que les valeurs minuscules, toute écriture de ``users.role`` échouait
en production PostgreSQL. Voir la migration 20260625_0036 et ``values_callable``
sur ``User.role``.
"""

from sqlalchemy import text

import app.db.session as db_session
from app.models import User, UserRole


def test_userrole_values_are_lowercase() -> None:
    """Le contrat externe (API JSON, type PG) repose sur des valeurs minuscules."""
    assert {r.value for r in UserRole} == {
        "technician",
        "officer",
        "admin",
        "accountant",
    }


def test_userrole_stored_as_lowercase_value(client) -> None:  # noqa: ANN001
    """``users.role`` doit être persisté avec la valeur minuscule, pas le nom.

    La fixture ``client`` seede le superuser (``role=UserRole.ADMIN``).
    """
    with db_session.SessionLocal() as session:
        raw = session.execute(text("SELECT role FROM users LIMIT 1")).scalar_one()
        assert raw == "admin", f"valeur brute attendue 'admin', obtenue {raw!r}"

        # Round-trip : la valeur brute est bien remappée sur le membre enum.
        user = session.query(User).first()
        assert user is not None
        assert user.role is UserRole.ADMIN
