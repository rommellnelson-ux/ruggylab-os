"""
Schémas Pydantic/Dataclasses — StockPredictor CMU Côte d'Ivoire.

Modèle logistique : Consommation Mensuelle Moyenne (CMM) OMS/MSF
  augmentée d'un profil saisonnier épidémiologique propre à la CI.

Niveaux d'alerte :
  RUPTURE_IMMINENTE  < 1 mois de stock restant
  ALERTE_CRITIQUE    1 – 2 mois
  ALERTE             2 – 3 mois
  OK                 > 3 mois
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AlertLevel(StrEnum):
    OK = "OK"
    ALERTE = "ALERTE"
    ALERTE_CRITIQUE = "ALERTE_CRITIQUE"
    RUPTURE_IMMINENTE = "RUPTURE_IMMINENTE"


class PredictionHorizon(IntEnum):
    THIRTY_DAYS = 30
    SIXTY_DAYS = 60
    NINETY_DAYS = 90
    SIX_MONTHS = 180


class DiseaseCategory(StrEnum):
    """Catégorie thérapeutique influençant le profil saisonnier CI."""

    ANTIMALARIAL = "ANTIMALARIAL"  # ACT, quinine, artémisinine
    ANTIBIOTIC = "ANTIBIOTIC"  # amoxicilline, cotrimoxazole
    ANALGESIC = "ANALGESIC"  # paracétamol, ibuprofène
    ANTIDIABETIC = "ANTIDIABETIC"  # metformine, insuline
    ANTIHYPERTENSIVE = "ANTIHYPERTENSIVE"  # amlodipine, énalapril
    RESPIRATORY = "RESPIRATORY"  # salbutamol, corticoïdes
    GENERAL = "GENERAL"  # profil neutre


# ---------------------------------------------------------------------------
# Données d'entrée
# ---------------------------------------------------------------------------


class DrugStockInput(BaseModel):
    """Données brutes d'un médicament pour la prédiction."""

    dci_code: Annotated[str, Field(min_length=2, examples=["ARTEMETHER-LUMEFANTRINE"])]
    current_stock: Annotated[int, Field(ge=0, description="Stock actuel (unités)")]
    cmm_units: Annotated[int, Field(gt=0, description="CMM de base (unités/mois)")]
    disease_category: DiseaseCategory = DiseaseCategory.GENERAL
    unit_cost_xof: Annotated[
        Decimal | None,
        Field(
            default=None,
            gt=Decimal("0"),
            description="Coût unitaire XOF (pour estimation commande)",
        ),
    ] = None

    @field_validator("dci_code")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.strip().upper()


class PredictionRequest(BaseModel):
    """Requête de prédiction de stocks."""

    drugs: Annotated[list[DrugStockInput], Field(min_length=1)]
    reference_date: date | None = Field(
        default=None,
        description="Date de référence (défaut : aujourd'hui)",
    )
    horizon_days: PredictionHorizon = PredictionHorizon.NINETY_DAYS
    include_fhir: bool = Field(
        default=False,
        description="Inclure un bundle FHIR MedicationRequest pour les réapprovisionnements",
    )


# ---------------------------------------------------------------------------
# Résultats de prédiction
# ---------------------------------------------------------------------------


class StockPredictionLine(BaseModel):
    """Prédiction pour un médicament donné."""

    dci_code: str
    disease_category: DiseaseCategory
    current_stock: int
    cmm_baseline: int
    seasonal_coefficient: float = Field(description="Facteur saisonnier du mois de référence")
    cmm_seasonal: float = Field(description="CMM ajusté par la saisonnalité")

    # Prédiction à l'horizon
    predicted_stock_at_horizon: float
    months_of_stock_remaining: float
    estimated_rupture_date: date | None

    # Alerte & commande
    alert_level: AlertLevel
    reorder_needed: bool
    suggested_order_qty: int
    reorder_cost_xof: Decimal | None


class PredictionResult(BaseModel):
    """Résultat complet de prédiction pour un ensemble de médicaments."""

    reference_date: date
    horizon_days: int
    drug_predictions: list[StockPredictionLine]

    # KPIs agrégés
    total_drugs: int
    critical_count: int = Field(description="RUPTURE_IMMINENTE + ALERTE_CRITIQUE")
    alert_count: int = Field(description="ALERTE uniquement")
    ok_count: int

    # FHIR optionnel
    fhir_medication_request: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Profil saisonnier (dataclass interne, non exposé via API)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeasonalProfile:
    """
    Coefficients mensuels de consommation pour une catégorie thérapeutique.

    Profil épidémiologique Côte d'Ivoire :
      - Saison des grandes pluies : avril – juillet  (pic paludisme)
      - Petites pluies            : octobre – novembre
      - Harmattan (saison sèche)  : décembre – février (IRA, méningite)
    """

    category: DiseaseCategory
    # Index 0 = janvier … index 11 = décembre
    monthly_coefficients: tuple[float, ...] = field(default_factory=tuple)

    def coefficient_for(self, month: int) -> float:
        """Retourne le coefficient pour un mois donné (1-12)."""
        return self.monthly_coefficients[month - 1]
