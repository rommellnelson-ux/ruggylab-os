"""Catalogue de référence des analytes POCT (source unique des bornes).

Centralise les intervalles de référence et seuils critiques des paramètres
mesurés au point de soin (Precis Expert : glycémie, cholestérol, acide urique,
lactate, corps cétoniques). Utilisé à la fois par le validateur historique
``PrecisExpertValidator`` et par la route générique ``/results/poct-batch``,
afin qu'une borne ne soit définie qu'à un seul endroit.

Ajouter un appareil POCT = ajouter ses analytes ici (pas de logique à écrire).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.dh36_interfacing import RuggylabJSONPoint


def calculate_status(value: float, low: float, high: float) -> str:
    """Statut normalisé : ``L`` (bas), ``H`` (haut) ou ``N`` (normal)."""
    if value < low:
        return "L"
    if value > high:
        return "H"
    return "N"


@dataclass(frozen=True)
class POCTAnalyteSpec:
    """Spécification clinique d'un analyte POCT."""

    code: str
    label: str
    default_unit: str
    low: float
    high: float
    critical_low: float | None = None
    critical_high: float | None = None
    # Intervalles différenciés par sexe, p. ex. {"M": (35.0, 72.0)}.
    # Les bornes ``low``/``high`` servent de valeurs par défaut.
    sex_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)

    def range_for(self, sex: str | None) -> tuple[float, float]:
        if sex and sex in self.sex_ranges:
            return self.sex_ranges[sex]
        return (self.low, self.high)


# Catalogue Precis Expert (appareil multifonction 5 paramètres).
POCT_ANALYTES: dict[str, POCTAnalyteSpec] = {
    "GLU": POCTAnalyteSpec(
        code="GLU",
        label="Glycémie",
        default_unit="g/L",
        low=0.7,
        high=1.10,
        critical_low=0.50,
        critical_high=3.0,
    ),
    "CHOL": POCTAnalyteSpec(
        code="CHOL",
        label="Cholestérol total",
        default_unit="g/L",
        low=1.4,
        high=2.0,
    ),
    "UA": POCTAnalyteSpec(
        code="UA",
        label="Acide urique",
        default_unit="mg/L",
        # Par défaut (sexe inconnu ou féminin) : intervalle femme.
        low=26.0,
        high=60.0,
        sex_ranges={"M": (35.0, 72.0), "F": (26.0, 60.0)},
    ),
    "LAC": POCTAnalyteSpec(
        code="LAC",
        label="Lactate",
        default_unit="mmol/L",
        low=0.5,
        high=2.2,
        critical_high=4.0,
    ),
    "KET": POCTAnalyteSpec(
        code="KET",
        label="Corps cétoniques",
        default_unit="mmol/L",
        low=0.0,
        high=0.6,
    ),
}

#: Codes acceptés par les routes POCT (vocabulaire fermé, anti-faute de frappe).
POCT_CODES = tuple(POCT_ANALYTES)


def build_poct_point(
    code: str,
    value: float,
    unit: str | None,
    sex: str | None,
) -> RuggylabJSONPoint:
    """Construit le point JSONB normalisé d'un analyte POCT.

    ``is_critical`` est porté par le point lui-même ; l'appelant agrège les
    points pour décider du caractère critique global du résultat.
    """
    spec = POCT_ANALYTES[code]
    low, high = spec.range_for(sex)
    is_critical = False
    if spec.critical_low is not None and value < spec.critical_low:
        is_critical = True
    if spec.critical_high is not None and value > spec.critical_high:
        is_critical = True
    return RuggylabJSONPoint(
        value=value,
        unit=unit or spec.default_unit,
        status=calculate_status(value, low, high),
        ref_range=f"{low}-{high}",
        is_critical=is_critical,
    )
