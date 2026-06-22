"""Vérification de prêt-au-déploiement (pré go-live) de RuggyLab OS.

Contrôle la configuration de l'instance courante : secrets robustes, base
PostgreSQL accessible et à jour des migrations, mot de passe admin non par
défaut. À lancer sur l'instance cible (mêmes variables d'environnement que le
serveur), AVANT d'ouvrir au public :

    python -m scripts.check_deploy_readiness

Sort 0 si prêt (aucun échec), 1 sinon. Les avertissements ne bloquent pas mais
doivent être revus.
"""

from __future__ import annotations

import sys

from sqlalchemy.engine import Engine

# Console Windows (cp1252) : éviter UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_fail = 0
_warn = 0


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def warn(msg: str) -> None:
    global _warn
    _warn += 1
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    global _fail
    _fail += 1
    print(f"  [FAIL] {msg}")


def check_secrets() -> None:
    # NB : on n'utilise pas settings.has_default_secret_key — son défaut lit déjà
    # la variable d'env, donc il vaut True pour toute clé fournie par l'env (y
    # compris une clé forte). On vérifie directement longueur et contenu.
    from app.core.config import settings

    sk = settings.SECRET_KEY or ""
    if len(sk) < 32 or "change_me" in sk.lower():
        fail("SECRET_KEY faible ou par défaut (>= 32 caractères, valeur unique requise).")
    else:
        ok("SECRET_KEY robuste.")

    pw = settings.FIRST_SUPERUSER_PASSWORD or ""
    if len(pw) < 16 or "change_me" in pw.lower():
        fail("FIRST_SUPERUSER_PASSWORD faible ou par défaut (>= 16 caractères requis).")
    else:
        ok("FIRST_SUPERUSER_PASSWORD robuste.")


def check_database() -> None:
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.session import engine

    if settings.DATABASE_URL.startswith("sqlite"):
        warn("DATABASE_URL pointe sur SQLite — privilégier PostgreSQL en production.")
    else:
        ok("DATABASE_URL non-SQLite (PostgreSQL attendu).")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ok("Base de données accessible.")
    except Exception as exc:  # noqa: BLE001
        fail(f"Base de données inaccessible : {exc}")
        return

    _check_migrations(engine)
    _check_admin_password(engine)


def _check_migrations(engine: Engine) -> None:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    try:
        script = ScriptDirectory.from_config(Config("alembic.ini"))
        heads = set(script.get_heads())
        with engine.connect() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
        if current == heads:
            ok(f"Migrations à jour (head {', '.join(sorted(heads)) or '—'}).")
        else:
            fail(
                f"Migrations non à jour : base={sorted(current) or '∅'} vs head={sorted(heads)}. "
                "Lancer `alembic upgrade head`."
            )
    except Exception as exc:  # noqa: BLE001
        fail(f"Impossible de vérifier les migrations : {exc}")


def _check_admin_password(engine: Engine) -> None:
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.core.security import verify_password
    from app.models import User

    try:
        with Session(engine) as s:
            admin = s.query(User).filter(User.username == settings.FIRST_SUPERUSER).first()
            if admin is None:
                warn(
                    f"Compte admin '{settings.FIRST_SUPERUSER}' introuvable (sera créé au démarrage)."
                )
                return
            if verify_password("change_me_admin_password", admin.hashed_password):
                fail("Le compte admin utilise encore le mot de passe par défaut de test.")
            else:
                ok("Mot de passe admin personnalisé.")
    except Exception as exc:  # noqa: BLE001
        warn(f"Vérification du mot de passe admin impossible : {exc}")


def main() -> int:
    print("Prêt-au-déploiement RuggyLab OS\n")
    print("Secrets & durcissement :")
    check_secrets()
    print("\nBase de données & migrations :")
    check_database()
    print(f"\nRésultat : {_fail} échec(s), {_warn} avertissement(s).")
    if _fail:
        print("NON PRÊT — corriger les échecs avant la mise en production.")
        return 1
    print("PRÊT pour la mise en production (revoir les avertissements éventuels).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
