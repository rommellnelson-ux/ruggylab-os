"""
StockPredictor — Planification et Logistique Prédictive CMU Côte d'Ivoire
=========================================================================

Modèle CMM étendu :
  CMM_saisonnier = CMM_baseline × coefficient_épidémiologique(mois, catégorie)

Profils saisonniers CI (données épidémiologiques OMS/PNLP 2023-2025) :
  - Antipaludéens   : pic avril-juillet (grandes pluies) + oct-nov (petites pluies)
  - Antibiotiques   : pic jan-fév (harmattan IRA) + mai-juin (pluies gastro)
  - Respiratoires   : pic déc-fév (harmattan) + mai (transition)
  - Antidiabétiques : stable toute l'année avec légère hausse festive déc-jan
  - Antihypertenseurs : pic chaleur mar-avr et stress fêtes déc-jan
  - Analgésiques    : légère saisonnalité, stable

Architecture :
  Python 3.11+ · OOP · Dataclasses · Type Hinting strict
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from app.schemas.stock_predictor import (
    AlertLevel,
    DiseaseCategory,
    DrugStockInput,
    PredictionHorizon,
    PredictionRequest,
    PredictionResult,
    SeasonalProfile,
    StockPredictionLine,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seuils d'alerte OMS/MSF (en mois de stock)
# ---------------------------------------------------------------------------

THRESHOLD_RUPTURE: Final[float] = 1.0  # < 1 mois → RUPTURE_IMMINENTE
THRESHOLD_CRITIQUE: Final[float] = 2.0  # 1-2 mois → ALERTE_CRITIQUE
THRESHOLD_ALERTE: Final[float] = 3.0  # 2-3 mois → ALERTE
SAFETY_STOCK_MONTHS: Final[float] = 2.0  # stock de sécurité cible
ORDER_UP_TO_MONTHS: Final[float] = 6.0  # niveau cible de commande

DAYS_PER_MONTH: Final[float] = 30.44  # moyenne grégorienne


# ---------------------------------------------------------------------------
# Profils saisonniers épidémiologiques — Côte d'Ivoire
# ---------------------------------------------------------------------------
#
# Coefficients mensuels (jan→déc) calibrés sur les données PNLP/OMS CI.
# 1.0 = consommation normale, > 1.0 = surconsommation saisonnière.

_PROFILES: Final[dict[DiseaseCategory, SeasonalProfile]] = {
    DiseaseCategory.ANTIMALARIAL: SeasonalProfile(
        category=DiseaseCategory.ANTIMALARIAL,
        monthly_coefficients=(
            0.80,  # Jan — saison sèche, peu de paludisme
            0.75,  # Fév — harmattan, minimum annuel
            0.90,  # Mar — début transition
            1.35,  # Avr — début grandes pluies ↑
            1.60,  # Mai — pic grandes pluies (max)
            1.50,  # Jun — grandes pluies
            1.35,  # Jul — fin grandes pluies
            0.95,  # Aoû — petite saison sèche
            1.00,  # Sep — transition
            1.30,  # Oct — petites pluies ↑
            1.20,  # Nov — fin petites pluies
            0.80,  # Déc — saison sèche
        ),
    ),
    DiseaseCategory.ANTIBIOTIC: SeasonalProfile(
        category=DiseaseCategory.ANTIBIOTIC,
        monthly_coefficients=(
            1.30,  # Jan — IRA harmattan
            1.35,  # Fév — pic harmattan (max IRA)
            1.10,  # Mar — transition
            1.00,  # Avr — retour normal
            1.15,  # Mai — gastro-entérites pluies
            1.20,  # Jun — pic gastro
            1.05,  # Jul
            0.90,  # Aoû
            0.90,  # Sep
            1.00,  # Oct
            1.00,  # Nov
            1.20,  # Déc — fêtes + début harmattan
        ),
    ),
    DiseaseCategory.RESPIRATORY: SeasonalProfile(
        category=DiseaseCategory.RESPIRATORY,
        monthly_coefficients=(
            1.40,  # Jan — harmattan max (asthme, toux)
            1.45,  # Fév — pic harmattan
            1.20,  # Mar — déclin
            1.00,  # Avr
            1.10,  # Mai — humidité
            1.05,  # Jun
            0.90,  # Jul
            0.85,  # Aoû
            0.85,  # Sep
            0.95,  # Oct
            1.05,  # Nov
            1.30,  # Déc — début harmattan
        ),
    ),
    DiseaseCategory.ANTIDIABETIC: SeasonalProfile(
        category=DiseaseCategory.ANTIDIABETIC,
        monthly_coefficients=(
            1.10,  # Jan — fêtes de fin d'année, excès alimentaires
            1.00,
            0.95,
            0.95,
            0.95,
            0.95,
            0.95,
            0.95,
            0.95,
            1.00,
            1.00,
            1.15,  # Déc — fêtes, excès alimentaires
        ),
    ),
    DiseaseCategory.ANTIHYPERTENSIVE: SeasonalProfile(
        category=DiseaseCategory.ANTIHYPERTENSIVE,
        monthly_coefficients=(
            1.10,  # Jan — stress post-fêtes
            1.05,
            1.15,  # Mar — chaleur intense
            1.20,  # Avr — chaleur max avant pluies
            1.00,
            0.95,
            0.95,
            0.95,
            0.95,
            1.00,
            1.00,
            1.15,  # Déc — stress fêtes
        ),
    ),
    DiseaseCategory.ANALGESIC: SeasonalProfile(
        category=DiseaseCategory.ANALGESIC,
        monthly_coefficients=(
            1.10,
            1.05,
            1.05,
            1.00,
            1.00,
            1.00,
            1.00,
            0.95,
            0.95,
            1.00,
            1.00,
            1.10,
        ),
    ),
    DiseaseCategory.GENERAL: SeasonalProfile(
        category=DiseaseCategory.GENERAL,
        # Profil neutre — légère saisonnalité harmonique
        monthly_coefficients=(
            1.05,
            1.00,
            1.00,
            1.00,
            1.05,
            1.05,
            1.00,
            0.95,
            0.95,
            1.00,
            1.00,
            1.05,
        ),
    ),
}


# ---------------------------------------------------------------------------
# Moteur de prédiction
# ---------------------------------------------------------------------------


@dataclass
class StockPredictor:
    """
    Prédicateur de stocks pharmaceutiques pour officines CMU-CI.

    Algorithme :
      1. Récupérer le profil saisonnier de la catégorie thérapeutique
      2. Calculer le CMM saisonnier = CMM_baseline × coeff(mois)
      3. Estimer la consommation sur l'horizon : C = CMM_saisonnier × (horizon/30.44)
      4. Stock résiduel = current_stock - C
      5. Mois de stock = current_stock / CMM_saisonnier
      6. Date de rupture estimée = ref_date + (current_stock / CMM_saisonnier) × 30.44 jours
      7. Quantité à commander = max(0, CMM × ORDER_UP_TO_MONTHS - current_stock)
      8. Niveau d'alerte selon les seuils OMS/MSF
    """

    profiles: dict[DiseaseCategory, SeasonalProfile] = field(
        default_factory=lambda: dict(_PROFILES)
    )

    def predict(self, request: PredictionRequest) -> PredictionResult:
        """Point d'entrée principal : calcule les prédictions pour tous les médicaments."""
        ref_date = request.reference_date or date.today()
        lines: list[StockPredictionLine] = []

        for drug in request.drugs:
            line = self._predict_drug(drug, ref_date, request.horizon_days)
            lines.append(line)
            logger.info(
                "stock_predictor.predict",
                extra={
                    "dci_code": drug.dci_code,
                    "alert_level": line.alert_level,
                    "months_remaining": round(line.months_of_stock_remaining, 2),
                    "reorder_needed": line.reorder_needed,
                },
            )

        # Tri par criticité décroissante
        lines.sort(key=lambda ln: self._alert_sort_key(ln.alert_level))

        critical = sum(
            1
            for ln in lines
            if ln.alert_level in (AlertLevel.RUPTURE_IMMINENTE, AlertLevel.ALERTE_CRITIQUE)
        )
        alerts = sum(1 for ln in lines if ln.alert_level == AlertLevel.ALERTE)
        ok = sum(1 for ln in lines if ln.alert_level == AlertLevel.OK)

        fhir = None
        if request.include_fhir:
            reorders = [ln for ln in lines if ln.reorder_needed]
            if reorders:
                fhir = self._build_fhir_medication_request(reorders, ref_date)

        return PredictionResult(
            reference_date=ref_date,
            horizon_days=int(request.horizon_days),
            drug_predictions=lines,
            total_drugs=len(lines),
            critical_count=critical,
            alert_count=alerts,
            ok_count=ok,
            fhir_medication_request=fhir,
        )

    # ------------------------------------------------------------------
    # Prédiction individuelle
    # ------------------------------------------------------------------

    def _predict_drug(
        self,
        drug: DrugStockInput,
        ref_date: date,
        horizon: PredictionHorizon,
    ) -> StockPredictionLine:
        profile = self.profiles[drug.disease_category]
        coeff = profile.coefficient_for(ref_date.month)
        cmm_seasonal = drug.cmm_units * coeff

        # Consommation estimée sur l'horizon
        horizon_months = horizon / DAYS_PER_MONTH
        consumption_at_horizon = cmm_seasonal * horizon_months
        predicted_stock = max(0.0, drug.current_stock - consumption_at_horizon)

        # Mois de stock restant (base saisonnière)
        months_remaining = drug.current_stock / cmm_seasonal if cmm_seasonal > 0 else float("inf")

        # Date de rupture estimée
        rupture_date: date | None = None
        if math.isfinite(months_remaining):
            days_to_rupture = int(months_remaining * DAYS_PER_MONTH)
            rupture_date = ref_date + timedelta(days=days_to_rupture)

        alert_level = self._compute_alert(months_remaining)
        reorder = months_remaining < SAFETY_STOCK_MONTHS

        # Quantité suggérée : viser ORDER_UP_TO_MONTHS de CMM saisonnier
        target_qty = int(math.ceil(cmm_seasonal * ORDER_UP_TO_MONTHS))
        suggested_order = max(0, target_qty - drug.current_stock)

        # Coût estimé de la commande
        reorder_cost: Decimal | None = None
        if drug.unit_cost_xof is not None and suggested_order > 0:
            reorder_cost = drug.unit_cost_xof * Decimal(suggested_order)

        return StockPredictionLine(
            dci_code=drug.dci_code,
            disease_category=drug.disease_category,
            current_stock=drug.current_stock,
            cmm_baseline=drug.cmm_units,
            seasonal_coefficient=round(coeff, 4),
            cmm_seasonal=round(cmm_seasonal, 2),
            predicted_stock_at_horizon=round(predicted_stock, 2),
            months_of_stock_remaining=round(months_remaining, 2),
            estimated_rupture_date=rupture_date,
            alert_level=alert_level,
            reorder_needed=reorder,
            suggested_order_qty=suggested_order,
            reorder_cost_xof=reorder_cost,
        )

    # ------------------------------------------------------------------
    # Niveau d'alerte
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_alert(months: float) -> AlertLevel:
        if months < THRESHOLD_RUPTURE:
            return AlertLevel.RUPTURE_IMMINENTE
        if months < THRESHOLD_CRITIQUE:
            return AlertLevel.ALERTE_CRITIQUE
        if months < THRESHOLD_ALERTE:
            return AlertLevel.ALERTE
        return AlertLevel.OK

    @staticmethod
    def _alert_sort_key(level: AlertLevel) -> int:
        """Ordre de tri : RUPTURE=0 (premier) … OK=3 (dernier)."""
        return {
            AlertLevel.RUPTURE_IMMINENTE: 0,
            AlertLevel.ALERTE_CRITIQUE: 1,
            AlertLevel.ALERTE: 2,
            AlertLevel.OK: 3,
        }[level]

    # ------------------------------------------------------------------
    # Génération FHIR MedicationRequest (bundle simplifié R4)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fhir_medication_request(
        reorders: list[StockPredictionLine],
        ref_date: date,
    ) -> dict[str, Any]:
        """
        Génère un bundle FHIR R4 MedicationRequest pour les réapprovisionnements.

        Chaque médicament en rupture imminente ou critique produit une ressource
        MedicationRequest avec :
          - statut : 'active'
          - intent : 'order'
          - medication : CodeableConcept DCI (system OMS)
          - quantité demandée : suggested_order_qty
          - priorité : 'urgent' si RUPTURE_IMMINENTE, 'routine' sinon
        """
        entries: list[dict[str, Any]] = []
        for idx, line in enumerate(reorders, start=1):
            priority = "urgent" if line.alert_level == AlertLevel.RUPTURE_IMMINENTE else "routine"
            entries.append(
                {
                    "fullUrl": f"urn:uuid:med-req-{idx:04d}",
                    "resource": {
                        "resourceType": "MedicationRequest",
                        "id": f"med-req-{idx:04d}",
                        "status": "active",
                        "intent": "order",
                        "priority": priority,
                        "medicationCodeableConcept": {
                            "coding": [
                                {
                                    "system": "http://www.whocc.no/atc",
                                    "code": line.dci_code,
                                    "display": line.dci_code,
                                }
                            ],
                            "text": line.dci_code,
                        },
                        "dispenseRequest": {
                            "quantity": {
                                "value": line.suggested_order_qty,
                                "unit": "unité",
                                "system": "http://unitsofmeasure.org",
                                "code": "1",
                            },
                            "validityPeriod": {
                                "start": ref_date.isoformat(),
                            },
                        },
                        "note": [
                            {
                                "text": (
                                    f"Alerte : {line.alert_level} — "
                                    f"{round(line.months_of_stock_remaining, 1)} mois de stock. "
                                    f"CMM saisonnier : {line.cmm_seasonal} unités/mois."
                                )
                            }
                        ],
                    },
                }
            )

        return {
            "resourceType": "Bundle",
            "type": "collection",
            "timestamp": ref_date.isoformat(),
            "total": len(entries),
            "entry": entries,
        }

    # ------------------------------------------------------------------
    # Intégration DB (calcul CMM depuis l'historique StockMovement)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_cmm_from_history(
        movements_last_n_months: list[float],
    ) -> int:
        """
        Calcule le CMM à partir d'une liste de consommations mensuelles historiques.

        Args:
            movements_last_n_months: consommations absolues (positives) par mois,
                                     de la plus ancienne à la plus récente.

        Returns:
            CMM arrondi à l'unité supérieure (règle OMS : toujours arrondir à la hausse).
        """
        if not movements_last_n_months:
            return 0
        # Exclure les mois à 0 (ruptures connues) pour ne pas biaiser la moyenne
        non_zero = [abs(m) for m in movements_last_n_months if m != 0]
        if not non_zero:
            return 0
        return math.ceil(sum(non_zero) / len(non_zero))


# ---------------------------------------------------------------------------
# Singleton applicatif
# ---------------------------------------------------------------------------

_predictor: StockPredictor | None = None


def get_stock_predictor() -> StockPredictor:
    """Factory / singleton FastAPI-injectable."""
    global _predictor
    if _predictor is None:
        _predictor = StockPredictor()
    return _predictor
