"""Auto-validation ISO 15189 §5.8.

Valide automatiquement un résultat si toutes les conditions configurées
dans ``AutoValidationConfig`` sont satisfaites :
  - Tous les analytes du panel ont un flag résolu ET normal (aucun analyte
    numérique laissé sans plage de référence — cf. ``_uncovered_analytes``)
  - Pas de delta inter-résultats dépassé
  - Pas de valeur critique

Aucune modification de la session n'est commitée ici ; l'appelant
doit faire le ``db.commit()`` après.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ruggylab_os import AutoValidationConfig, Result
from app.services.critical_checker import _extract_numeric
from app.utils.datetime_utils import utcnow_naive

# Jetons de flag considérés « normaux ». Deux vocabulaires coexistent dans
# ``result.flags`` : le vocabulaire court officiel
# (``compute_flags`` → N/H/L/HH/LL) et, par tolérance défensive, quelques formes
# longues historiques (NORMAL/BAS/HAUT/CRITIQUE …/NÉGATIF).
# Le chemin ``apply_bioref_to_result`` actuel ne modifie pas ``result.flags``.
_NORMAL_FLAGS = {"N", "NORMAL", "NÉGATIF", "NEGATIF"}

# Clés de ``data_points`` qui ne sont pas des analytes cliniques (métadonnées).
# Miroir de ``results._NON_ANALYTIC_KEYS`` (dupliqué pour éviter un import
# circulaire : ``results`` importe déjà ce module).
_NON_ANALYTIC_KEYS_UPPER = {"MANUAL_ENTRY_BY", "ENTRY_TIMESTAMP", "CALIBRATION", "OVERALL_FLAGS"}


def _is_normal_flag(value: object) -> bool:
    return isinstance(value, str) and value.strip().upper() in _NORMAL_FLAGS


def _uncovered_analytes(result: Result) -> set[str]:
    """Analytes numériques du panel sans flag résolu (upper-case).

    Un analyte présent dans ``data_points`` mais absent de ``flags`` n'a été
    confronté à aucune plage de référence : sa normalité n'est pas confirmée.
    """
    covered = {str(k).upper() for k in (result.flags or {})}
    numeric = {
        k.upper()
        for k, raw in (result.data_points or {}).items()
        if isinstance(k, str)
        and k.upper() not in _NON_ANALYTIC_KEYS_UPPER
        and _extract_numeric(raw) is not None
    }
    return numeric - covered


def _active_config(db: Session) -> AutoValidationConfig | None:
    """Règle active à appliquer : la plus récente (id décroissant), déterministe."""
    return (
        db.query(AutoValidationConfig)
        .filter(AutoValidationConfig.is_active.is_(True))
        .order_by(AutoValidationConfig.id.desc())
        .first()
    )


def try_auto_validate(result: Result, db: Session) -> bool:
    """Tente d'auto-valider ``result``.

    Retourne ``True`` si la règle s'applique et que le résultat a été marqué
    auto-validé, ``False`` sinon.  Ne commite pas la session.
    """
    config = _active_config(db)
    if not config:
        return False

    # ── Condition 1 : pas de valeur critique ──────────────────────────────────
    if config.require_not_critical and result.is_critical:
        return False

    # ── Condition 2 : pas de delta inter-résultats ────────────────────────────
    if config.require_no_delta and result.delta_exceeded:
        return False

    # ── Condition 3 : tous les analytes contrôlés et normaux ──────────────────
    if config.require_all_flags_normal:
        flags = result.flags
        # flags=None or {} → plages de référence non configurées → impossible
        # de confirmer la normalité → ne pas auto-valider
        if not flags:
            return False
        if any(not _is_normal_flag(v) for v in flags.values()):
            return False
        # Garde-fou couverture (ISO 15189 §5.8) : chaque analyte numérique du
        # panel doit avoir été confronté à une plage de référence. Un analyte
        # sans plage configurée n'apparaît pas dans ``flags`` → on s'abstient.
        if _uncovered_analytes(result):
            return False

    result.is_auto_validated = True
    result.auto_validated_at = utcnow_naive()
    return True


def batch_auto_validate(db: Session, limit: int = 200) -> dict:
    """Applique l'auto-validation sur les résultats validés non encore traités.

    Retourne ``{"processed": int, "auto_validated": int}``.
    """
    config = _active_config(db)
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
