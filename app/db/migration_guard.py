"""Verrou de démarrage : refuser de servir si le schéma n'est pas au head Alembic.

Le service ``migrate`` (docker compose) est manuel : sans ce verrou, un
opérateur qui omet l'étape démarre l'application contre une base au schéma
ancien — erreurs silencieuses ou corruption. Ici, on échoue vite et clair.

Échappatoire assumée : ``SKIP_MIGRATION_CHECK=1`` (diagnostic d'urgence
uniquement, jamais en fonctionnement normal).
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def get_script_head() -> str:
    """Head attendu par le code (fichiers alembic/versions embarqués)."""
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        raise RuntimeError("Aucune migration Alembic trouvée dans le dépôt.")
    return head


def get_db_revision(engine: Engine) -> str | None:
    """Révision appliquée à la base, ou None si alembic_version est absente."""
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 — table absente / base vierge
        return None


def assert_migrations_up_to_date(engine: Engine) -> None:
    """Lève RuntimeError si la base n'est pas exactement au head embarqué."""
    head = get_script_head()
    db_rev = get_db_revision(engine)
    if db_rev == head:
        logger.info("Migration guard: schéma à jour (head=%s).", head)
        return
    raise RuntimeError(
        f"Le schéma de la base ({db_rev or 'aucune révision Alembic'}) ne correspond pas "
        f"au head attendu par cette image ({head}). Exécuter `alembic upgrade head` "
        f"(docker compose --profile migrate run --rm migrate) avant de démarrer. "
        f"Échappatoire de diagnostic : SKIP_MIGRATION_CHECK=1."
    )
