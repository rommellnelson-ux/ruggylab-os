"""
Tests du StockPredictor CMU Côte d'Ivoire
==========================================

Couverture :
  - Profils saisonniers (12 mois × 7 catégories)
  - Calcul CMM saisonnier et prédiction à l'horizon
  - Niveaux d'alerte OMS/MSF (RUPTURE / CRITIQUE / ALERTE / OK)
  - Date de rupture estimée
  - Quantités de commande suggérées
  - Calcul CMM depuis historique (méthode OMS)
  - Bundle FHIR MedicationRequest
  - Tri par criticité
  - Cas limites (stock=0, CMM élevé, stock très élevé)
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import pytest

from app.schemas.stock_predictor import (
    AlertLevel,
    DiseaseCategory,
    DrugStockInput,
    PredictionHorizon,
    PredictionRequest,
)
from app.services.stock_predictor import (
    _PROFILES,
    DAYS_PER_MONTH,
    ORDER_UP_TO_MONTHS,
    SAFETY_STOCK_MONTHS,
    THRESHOLD_ALERTE,
    THRESHOLD_CRITIQUE,
    THRESHOLD_RUPTURE,
    StockPredictor,
    get_stock_predictor,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def predictor() -> StockPredictor:
    return StockPredictor()


def _drug(
    dci: str = "ARTEMETHER-LUMEFANTRINE",
    stock: int = 200,
    cmm: int = 100,
    category: DiseaseCategory = DiseaseCategory.ANTIMALARIAL,
    unit_cost: str | None = None,
) -> DrugStockInput:
    return DrugStockInput(
        dci_code=dci,
        current_stock=stock,
        cmm_units=cmm,
        disease_category=category,
        unit_cost_xof=Decimal(unit_cost) if unit_cost else None,
    )


def _request(
    drugs: list[DrugStockInput] | None = None,
    ref_date: date | None = None,
    horizon: PredictionHorizon = PredictionHorizon.NINETY_DAYS,
    include_fhir: bool = False,
) -> PredictionRequest:
    return PredictionRequest(
        drugs=drugs or [_drug()],
        reference_date=ref_date,
        horizon_days=horizon,
        include_fhir=include_fhir,
    )


# ===========================================================================
# 1. Profils saisonniers
# ===========================================================================


class TestSeasonalProfiles:
    def test_all_categories_have_profiles(self) -> None:
        for cat in DiseaseCategory:
            assert cat in _PROFILES, f"Profil manquant pour {cat}"

    def test_each_profile_has_12_months(self) -> None:
        for cat, profile in _PROFILES.items():
            assert len(profile.monthly_coefficients) == 12, (
                f"{cat} : attendu 12 coefficients, reçu {len(profile.monthly_coefficients)}"
            )

    def test_all_coefficients_positive(self) -> None:
        for cat, profile in _PROFILES.items():
            for i, coeff in enumerate(profile.monthly_coefficients, start=1):
                assert coeff > 0, f"{cat} mois {i} : coefficient ≤ 0"

    def test_antimalarial_peak_in_rainy_season(self) -> None:
        """Pic paludisme : mai (index 5) doit être > décembre (index 12)."""
        profile = _PROFILES[DiseaseCategory.ANTIMALARIAL]
        assert profile.coefficient_for(5) > profile.coefficient_for(12)

    def test_antimalarial_peak_in_may(self) -> None:
        """Mai doit avoir le coefficient le plus élevé pour les antipaludéens."""
        profile = _PROFILES[DiseaseCategory.ANTIMALARIAL]
        may_coeff = profile.coefficient_for(5)
        assert all(may_coeff >= profile.coefficient_for(m) for m in range(1, 13))

    def test_respiratory_peak_in_harmattan(self) -> None:
        """Harmattan (jan-fév) : pic respiratoire."""
        profile = _PROFILES[DiseaseCategory.RESPIRATORY]
        assert profile.coefficient_for(2) > profile.coefficient_for(7)

    def test_coefficient_for_valid_months(self) -> None:
        profile = _PROFILES[DiseaseCategory.GENERAL]
        for month in range(1, 13):
            coeff = profile.coefficient_for(month)
            assert isinstance(coeff, float)
            assert coeff > 0

    def test_seasonal_profile_frozen(self) -> None:
        """SeasonalProfile est un dataclass frozen — immuable."""
        profile = _PROFILES[DiseaseCategory.GENERAL]
        with pytest.raises((AttributeError, TypeError)):
            profile.category = DiseaseCategory.ANTIBIOTIC  # type: ignore[misc]


# ===========================================================================
# 2. Calcul CMM saisonnier
# ===========================================================================


class TestCMMSeasonal:
    def test_cmm_seasonal_equals_baseline_times_coeff(self, predictor: StockPredictor) -> None:
        """CMM saisonnier = CMM_baseline × coefficient du mois."""
        ref = date(2026, 5, 1)  # mai → coeff 1.60 pour antipaludéen
        drug = _drug(cmm=100, category=DiseaseCategory.ANTIMALARIAL)
        result = predictor.predict(_request([drug], ref_date=ref))
        line = result.drug_predictions[0]

        expected_coeff = _PROFILES[DiseaseCategory.ANTIMALARIAL].coefficient_for(5)
        assert line.seasonal_coefficient == pytest.approx(expected_coeff, abs=0.0001)
        assert line.cmm_seasonal == pytest.approx(100 * expected_coeff, abs=0.01)

    def test_general_category_near_neutral(self, predictor: StockPredictor) -> None:
        """Catégorie GENERAL : coefficient proche de 1.0."""
        ref = date(2026, 8, 1)  # août — coefficient 0.95
        drug = _drug(cmm=50, category=DiseaseCategory.GENERAL)
        result = predictor.predict(_request([drug], ref_date=ref))
        line = result.drug_predictions[0]
        assert 0.8 <= line.seasonal_coefficient <= 1.2

    def test_dci_code_normalised_to_uppercase(self, predictor: StockPredictor) -> None:
        drug = DrugStockInput(
            dci_code="artemether-lumefantrine",
            current_stock=100,
            cmm_units=50,
        )
        result = predictor.predict(_request([drug]))
        assert result.drug_predictions[0].dci_code == "ARTEMETHER-LUMEFANTRINE"


# ===========================================================================
# 3. Niveaux d'alerte OMS/MSF
# ===========================================================================


class TestAlertLevels:
    """Vérifie les seuils : RUPTURE < 1 mois / CRITIQUE 1-2 / ALERTE 2-3 / OK > 3."""

    def _months_to_stock(self, months: float, cmm_seasonal: float) -> int:
        return int(math.ceil(months * cmm_seasonal))

    def test_ok_level(self, predictor: StockPredictor) -> None:
        """> 3 mois de stock → OK."""
        ref = date(2026, 1, 1)
        coeff = _PROFILES[DiseaseCategory.GENERAL].coefficient_for(1)  # 1.05
        cmm_s = 100 * coeff
        stock = self._months_to_stock(4.0, cmm_s)  # 4 mois → OK
        drug = _drug(stock=stock, cmm=100, category=DiseaseCategory.GENERAL)
        line = predictor.predict(_request([drug], ref_date=ref)).drug_predictions[0]
        assert line.alert_level == AlertLevel.OK
        assert not line.reorder_needed

    def test_alerte_level(self, predictor: StockPredictor) -> None:
        """2-3 mois de stock → ALERTE."""
        ref = date(2026, 1, 1)
        coeff = _PROFILES[DiseaseCategory.GENERAL].coefficient_for(1)
        stock = self._months_to_stock(2.5, 100 * coeff)
        drug = _drug(stock=stock, cmm=100, category=DiseaseCategory.GENERAL)
        line = predictor.predict(_request([drug], ref_date=ref)).drug_predictions[0]
        assert line.alert_level == AlertLevel.ALERTE

    def test_alerte_critique_level(self, predictor: StockPredictor) -> None:
        """1-2 mois de stock → ALERTE_CRITIQUE."""
        ref = date(2026, 1, 1)
        coeff = _PROFILES[DiseaseCategory.GENERAL].coefficient_for(1)
        stock = self._months_to_stock(1.5, 100 * coeff)
        drug = _drug(stock=stock, cmm=100, category=DiseaseCategory.GENERAL)
        line = predictor.predict(_request([drug], ref_date=ref)).drug_predictions[0]
        assert line.alert_level == AlertLevel.ALERTE_CRITIQUE
        assert line.reorder_needed

    def test_rupture_imminente_level(self, predictor: StockPredictor) -> None:
        """< 1 mois de stock → RUPTURE_IMMINENTE."""
        drug = _drug(stock=10, cmm=100)  # 0.1 mois de stock
        line = predictor.predict(_request([drug])).drug_predictions[0]
        assert line.alert_level == AlertLevel.RUPTURE_IMMINENTE
        assert line.reorder_needed

    def test_zero_stock_is_rupture(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=0, cmm=100)
        line = predictor.predict(_request([drug])).drug_predictions[0]
        assert line.alert_level == AlertLevel.RUPTURE_IMMINENTE
        assert line.months_of_stock_remaining == 0.0


# ===========================================================================
# 4. Prédiction à l'horizon
# ===========================================================================


class TestHorizonPrediction:
    def test_predicted_stock_decreases_over_horizon(self, predictor: StockPredictor) -> None:
        """Le stock prévu à l'horizon doit être inférieur au stock actuel."""
        drug = _drug(stock=500, cmm=50)
        line = predictor.predict(
            _request([drug], horizon=PredictionHorizon.NINETY_DAYS)
        ).drug_predictions[0]
        assert line.predicted_stock_at_horizon < drug.current_stock

    def test_predicted_stock_never_negative(self, predictor: StockPredictor) -> None:
        """Le stock prévu ne peut pas être négatif."""
        drug = _drug(stock=10, cmm=500)  # rupture quasi-immédiate
        line = predictor.predict(_request([drug])).drug_predictions[0]
        assert line.predicted_stock_at_horizon >= 0.0

    def test_longer_horizon_means_lower_stock(self, predictor: StockPredictor) -> None:
        ref = date(2026, 6, 1)
        drug = _drug(stock=1000, cmm=100)
        r30 = predictor.predict(
            _request([drug], ref_date=ref, horizon=PredictionHorizon.THIRTY_DAYS)
        )
        r90 = predictor.predict(
            _request([drug], ref_date=ref, horizon=PredictionHorizon.NINETY_DAYS)
        )
        assert (
            r30.drug_predictions[0].predicted_stock_at_horizon
            > r90.drug_predictions[0].predicted_stock_at_horizon
        )

    def test_rupture_date_in_future(self, predictor: StockPredictor) -> None:
        ref = date(2026, 5, 1)
        drug = _drug(stock=200, cmm=100)
        line = predictor.predict(_request([drug], ref_date=ref)).drug_predictions[0]
        if line.estimated_rupture_date:
            assert line.estimated_rupture_date > ref

    def test_rupture_date_none_for_large_stock(self, predictor: StockPredictor) -> None:
        """Un stock très élevé peut résulter en une date de rupture dans le futur lointain
        mais jamais None pour un CMM > 0."""
        drug = _drug(stock=100_000, cmm=1)
        line = predictor.predict(_request([drug])).drug_predictions[0]
        # months_remaining sera très grand mais fini
        assert math.isfinite(line.months_of_stock_remaining)
        assert line.estimated_rupture_date is not None


# ===========================================================================
# 5. Quantités de commande
# ===========================================================================


class TestReorderQuantities:
    def test_suggested_order_targets_6_months(self, predictor: StockPredictor) -> None:
        """Quantité suggérée = ceil(CMM_saisonnier × 6) - stock_actuel."""
        ref = date(2026, 8, 1)  # août, coeff GENERAL ~0.95
        drug = _drug(stock=50, cmm=100, category=DiseaseCategory.GENERAL)
        line = predictor.predict(_request([drug], ref_date=ref)).drug_predictions[0]
        expected = max(
            0, int(math.ceil(line.cmm_seasonal * ORDER_UP_TO_MONTHS)) - drug.current_stock
        )
        assert line.suggested_order_qty == expected

    def test_no_order_when_stock_adequate(self, predictor: StockPredictor) -> None:
        """Si le stock dépasse ORDER_UP_TO_MONTHS × CMM, commande = 0."""
        drug = _drug(stock=10_000, cmm=100)
        line = predictor.predict(_request([drug])).drug_predictions[0]
        assert line.suggested_order_qty == 0

    def test_reorder_cost_computed_when_unit_cost_provided(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=10, cmm=100, unit_cost="500")
        line = predictor.predict(_request([drug])).drug_predictions[0]
        assert line.reorder_cost_xof is not None
        assert line.reorder_cost_xof == Decimal("500") * line.suggested_order_qty

    def test_no_reorder_cost_without_unit_cost(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=10, cmm=100, unit_cost=None)
        line = predictor.predict(_request([drug])).drug_predictions[0]
        assert line.reorder_cost_xof is None


# ===========================================================================
# 6. Résultat agrégé et tri
# ===========================================================================


class TestAggregatedResult:
    def test_sorting_critical_first(self, predictor: StockPredictor) -> None:
        """Les médicaments RUPTURE_IMMINENTE doivent apparaître en premier."""
        drugs = [
            _drug("AMOXICILLIN", stock=5000, cmm=50),  # OK
            _drug("ARTEMETHER-LUMEFANTRINE", stock=5, cmm=200),  # RUPTURE
            _drug("PARACETAMOL", stock=300, cmm=200),  # ALERTE
        ]
        result = predictor.predict(_request(drugs))
        levels = [ln.alert_level for ln in result.drug_predictions]
        assert levels[0] == AlertLevel.RUPTURE_IMMINENTE
        assert levels[-1] == AlertLevel.OK

    def test_counts_are_correct(self, predictor: StockPredictor) -> None:
        drugs = [
            _drug("AC", stock=5, cmm=200),  # RUPTURE
            _drug("BC", stock=80, cmm=100),  # ALERTE_CRITIQUE (~0.8 mois)
            _drug("CD", stock=250, cmm=100),  # ALERTE (~2.5 mois)
            _drug("DE", stock=500, cmm=100),  # OK (~5 mois)
        ]
        result = predictor.predict(_request(drugs, ref_date=date(2026, 8, 1)))
        assert result.total_drugs == 4
        assert result.critical_count >= 1  # au moins RUPTURE
        assert result.ok_count >= 1

    def test_default_reference_date_is_today(self, predictor: StockPredictor) -> None:
        result = predictor.predict(_request())
        assert result.reference_date == date.today()

    def test_horizon_reflected_in_result(self, predictor: StockPredictor) -> None:
        result = predictor.predict(_request(horizon=PredictionHorizon.SIX_MONTHS))
        assert result.horizon_days == 180

    def test_singleton_factory(self) -> None:
        p1 = get_stock_predictor()
        p2 = get_stock_predictor()
        assert p1 is p2


# ===========================================================================
# 7. Calcul CMM depuis historique OMS
# ===========================================================================


class TestCMMFromHistory:
    def test_basic_cmm_average(self, predictor: StockPredictor) -> None:
        cmm = predictor.compute_cmm_from_history([100.0, 120.0, 110.0])
        assert cmm == 110  # ceil(330/3) = ceil(110.0) = 110

    def test_zero_months_excluded(self, predictor: StockPredictor) -> None:
        """Les mois à 0 (ruptures) sont exclus de la moyenne."""
        cmm = predictor.compute_cmm_from_history([100.0, 0.0, 200.0])
        assert cmm == 150  # ceil((100+200)/2), pas (300/3=100)

    def test_all_zeros_returns_zero(self, predictor: StockPredictor) -> None:
        cmm = predictor.compute_cmm_from_history([0.0, 0.0, 0.0])
        assert cmm == 0

    def test_empty_history_returns_zero(self, predictor: StockPredictor) -> None:
        cmm = predictor.compute_cmm_from_history([])
        assert cmm == 0

    def test_always_rounds_up(self, predictor: StockPredictor) -> None:
        """OMS : toujours arrondir à l'unité supérieure."""
        cmm = predictor.compute_cmm_from_history([100.1, 100.2])
        # mean = 100.15 → ceil = 101
        assert cmm == 101

    def test_negative_values_treated_as_absolute(self, predictor: StockPredictor) -> None:
        """Les sorties de stock négatives sont traitées en valeur absolue."""
        cmm = predictor.compute_cmm_from_history([-100.0, -120.0])
        assert cmm == 110  # ceil((100+120)/2)


# ===========================================================================
# 8. Bundle FHIR MedicationRequest
# ===========================================================================


class TestFHIRMedicationRequest:
    def test_fhir_bundle_generated_when_requested(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=5, cmm=200)  # RUPTURE
        result = predictor.predict(_request([drug], include_fhir=True))
        assert result.fhir_medication_request is not None

    def test_fhir_bundle_none_when_not_requested(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=5, cmm=200)
        result = predictor.predict(_request([drug], include_fhir=False))
        assert result.fhir_medication_request is None

    def test_fhir_bundle_none_when_all_ok(self, predictor: StockPredictor) -> None:
        """Aucun bundle FHIR si aucun réapprovisionnement nécessaire."""
        drug = _drug(stock=50_000, cmm=100)
        result = predictor.predict(_request([drug], include_fhir=True))
        assert result.fhir_medication_request is None

    def test_fhir_bundle_structure(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=5, cmm=200)
        result = predictor.predict(_request([drug], include_fhir=True))
        bundle = result.fhir_medication_request
        assert bundle is not None
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "collection"
        assert "entry" in bundle
        assert len(bundle["entry"]) >= 1

    def test_fhir_rupture_has_urgent_priority(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=5, cmm=500)  # RUPTURE_IMMINENTE
        result = predictor.predict(_request([drug], include_fhir=True))
        bundle = result.fhir_medication_request
        assert bundle is not None
        entry = bundle["entry"][0]["resource"]
        assert entry["priority"] == "urgent"

    def test_fhir_medication_has_dci_code(self, predictor: StockPredictor) -> None:
        drug = _drug("AMOXICILLIN", stock=5, cmm=200)
        result = predictor.predict(_request([drug], include_fhir=True))
        bundle = result.fhir_medication_request
        assert bundle is not None
        coding = bundle["entry"][0]["resource"]["medicationCodeableConcept"]["coding"][0]
        assert coding["code"] == "AMOXICILLIN"

    def test_fhir_quantity_matches_suggested_order(self, predictor: StockPredictor) -> None:
        drug = _drug(stock=5, cmm=200)
        result = predictor.predict(_request([drug], include_fhir=True))
        line = result.drug_predictions[0]
        bundle = result.fhir_medication_request
        assert bundle is not None
        qty = bundle["entry"][0]["resource"]["dispenseRequest"]["quantity"]["value"]
        assert qty == line.suggested_order_qty


# ===========================================================================
# 9. Invariants et constantes réglementaires
# ===========================================================================


class TestConstants:
    def test_safety_stock_threshold_is_2_months(self) -> None:
        assert SAFETY_STOCK_MONTHS == 2.0

    def test_order_target_is_6_months(self) -> None:
        assert ORDER_UP_TO_MONTHS == 6.0

    def test_alert_thresholds_ordered(self) -> None:
        assert THRESHOLD_RUPTURE < THRESHOLD_CRITIQUE < THRESHOLD_ALERTE

    def test_days_per_month_gregorian(self) -> None:
        assert DAYS_PER_MONTH == pytest.approx(30.44, abs=0.01)

    def test_reorder_threshold_aligns_with_safety_stock(self) -> None:
        """Le seuil de commande doit être aligné avec SAFETY_STOCK_MONTHS."""
        assert SAFETY_STOCK_MONTHS == THRESHOLD_CRITIQUE
