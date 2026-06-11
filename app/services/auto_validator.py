"""Auto-validation ISO 15189 §5.8.

Valide automatiquement un résultat si toutes les conditions configurées
dans ``AutoValidationConfig`` sont satisfaites :
  - Tous les flags HH/H/N/L/LL = « N » (normal)
  - Pas de delta inter-résultats dépassé
  - Pas de valeur critique

Aucune modification de la session n'est commitée ici ; l'appelant
doit faire le ``db.commit()`` après.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ruggylab_os import AutoValidationConfig, Result
from app.utils.datetime_utils import utcnow_naive


def try_auto_validate(result: Result, db: Session) -> bool:
    """Tente d'auto-valider ``result``.

    Retourne ``True`` si la règle s'applique et que le résultat a été marqué
    auto-validé, ``False`` sinon.  Ne commite pas la session.
    """
    config: AutoValidationConfig | None = (
        db.query(AutoValidationConfig).filter(AutoValidationConfig.is_active.is_(True)).first()
    )
    if not config:
        return False

    # ── Condition 1 : pas de valeur critique ──────────────────────────────────
    if config.require_not_critical and result.is_critical:
        return False

    # ── Condition 2 : pas de delta inter-résultats ────────────────────────────
    if config.require_no_delta and result.delta_exceeded:
        return False

    # ── Condition 3 : tous les flags = N ─────────────────────────────────────
    if config.require_all_flags_normal:
        flags = result.flags
        # flags=None or {} → plages de référence non configurées → impossible
        # de confirmer la normalité → ne pas auto-valider
        if not flags:
            return False
        if any(v != "N" for v in flags.values()):
            return False

    result.is_auto_validated = True
    result.auto_validated_at = utcnow_naive()
    return True


def batch_auto_validate(db: Session, limit: int = 200) -> dict:
    """Applique l'auto-validation sur les résultats validés non encore traités.

    Retourne ``{"processed": int, "auto_validated": int}``.
    """
    config: AutoValidationConfig | None = (
        db.query(AutoValidationConfig).filter(AutoValidationConfig.is_active.is_(True)).first()
    )
    if not config:
        return {"processed": 0, "auto_validated": 0, "error": "Aucune règle active"}

    pending = (
        db.query(Result)
        .filter(Result.is_validated.is_(True), Result.is_auto_validated.is_(False))
        .limit(limit)
        .all()
    )
    validated = sum(1 for r in pending if try_auto_validate(r, db))
    db.commit()
    return {"processed": len(pending), "auto_validated": validated}
