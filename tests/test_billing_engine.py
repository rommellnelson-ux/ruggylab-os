"""
Tests du Moteur de Facturation CMU Côte d'Ivoire
=================================================

Couverture :
  - Validation des codes CIM-10 et DCI
  - Calcul CNAM 70 % / Ticket Modérateur 30 % (patient assuré)
  - Tarification non-assuré + programmes de remise
  - Plan de paiement fractionné BNPL
  - Rapport CMM (Consommation Mensuelle Moyenne) OMS/MSF
  - Invariants réglementaires et cas limites
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.billing import (
    BillingRequest,
    CIM10Code,
    CMMReportRequest,
    DCICode,
    DiagnosisLineRequest,
    DiscountProgram,
    DrugLineRequest,
    PatientType,
    PaymentMethod,
)
from app.services.billing_engine import (
    TAUX_CNAM,
    TICKET_MODERATEUR,
    BillingEngine,
    get_billing_engine,
)

# ---------------------------------------------------------------------------
# Fixtures communes
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> BillingEngine:
    return BillingEngine()


def _diagnosis(code: str = "B54", is_primary: bool = True) -> DiagnosisLineRequest:
    """Fabrique un diagnostic CIM-10 valide (défaut : B54 Paludisme)."""
    return DiagnosisLineRequest(cim10=CIM10Code(code=code), is_primary=is_primary)


def _drug(
    dci: str = "ARTEMETHER-LUMEFANTRINE",
    quantity: int = 6,
    unit_price: str = "1000",
    is_generic: bool = False,
) -> DrugLineRequest:
    """Fabrique une ligne médicament DCI valide."""
    return DrugLineRequest(
        dci=DCICode(code=dci),
        quantity=quantity,
        unit_price_xof=Decimal(unit_price),
        is_generic=is_generic,
    )


def _insured_request(**kwargs) -> BillingRequest:
    return BillingRequest(
        patient_type=PatientType.INSURED,
        insurance_id="CNAM-CI-2026-001234",
        diagnoses=[_diagnosis()],
        drugs=[_drug()],
        **kwargs,
    )


def _uninsured_request(**kwargs) -> BillingRequest:
    return BillingRequest(
        patient_type=PatientType.UNINSURED,
        diagnoses=[_diagnosis()],
        drugs=[_drug()],
        **kwargs,
    )


# ===========================================================================
# 1. Validation des codes réglementaires
# ===========================================================================


class TestCIM10Validation:
    """Codes CIM-10 : format lettre + 2 chiffres [+ point + 1-3 chars]."""

    @pytest.mark.parametrize(
        "code",
        ["B54", "J06.9", "Z29.11", "A00", "T14.0", "F32.1A"],
    )
    def test_valid_codes(self, code: str) -> None:
        obj = CIM10Code(code=code)
        assert obj.code == code.upper()

    @pytest.mark.parametrize(
        "bad_code",
        ["54B", "B5", "BCDE", "B54.12345", "b54", "B54.", "B-54"],
    )
    def test_invalid_codes_raise(self, bad_code: str) -> None:
        with pytest.raises(ValidationError, match="CIM-10"):
            CIM10Code(code=bad_code)

    def test_lowercase_is_normalised(self) -> None:
        obj = CIM10Code(code="b54")
        # b54 matches the regex after upper() → B54
        assert obj.code == "B54"


class TestDCIValidation:
    """Codes DCI : alphanumériques OMS, min 3 caractères."""

    @pytest.mark.parametrize(
        "code",
        ["AMOXICILLIN", "ARTEMETHER-LUMEFANTRINE", "ABC", "METFORMIN-HCL"],
    )
    def test_valid_dci(self, code: str) -> None:
        obj = DCICode(code=code)
        assert obj.code == code.upper()

    @pytest.mark.parametrize("bad", ["AB", "", "amox icillin", "!DRUG"])
    def test_invalid_dci_raise(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            DCICode(code=bad)


# ===========================================================================
# 2. Invariants du moteur
# ===========================================================================


class TestBillingEngineInvariants:
    def test_taux_sum_to_one(self, engine: BillingEngine) -> None:
        assert engine.taux_cnam + engine.ticket_moderateur == Decimal("1")

    def test_custom_rates_valid(self) -> None:
        eng = BillingEngine(taux_cnam=Decimal("0.80"), ticket_moderateur=Decimal("0.20"))
        assert eng.taux_cnam == Decimal("0.80")

    def test_inconsistent_rates_raise(self) -> None:
        with pytest.raises(ValueError, match="égale à 1"):
            BillingEngine(taux_cnam=Decimal("0.60"), ticket_moderateur=Decimal("0.30"))

    def test_singleton_factory(self) -> None:
        e1 = get_billing_engine()
        e2 = get_billing_engine()
        assert e1 is e2


# ===========================================================================
# 3. Patient ASSURÉ — Règle CNAM 70 / 30
# ===========================================================================


class TestInsuredBilling:
    def test_basic_split_70_30(self, engine: BillingEngine) -> None:
        """6 comprimés × 1 000 XOF = 6 000 XOF → CNAM 4 200 / patient 1 800."""
        req = _insured_request()
        result = engine.process(req)

        assert result.gross_total_xof == Decimal("6000")
        assert result.net_total_xof == Decimal("6000")
        assert result.cnam_coverage_xof == Decimal("4200")
        assert result.patient_due_xof == Decimal("1800")
        assert result.discount_amount_xof == Decimal("0")

    def test_cnam_plus_patient_equals_net(self, engine: BillingEngine) -> None:
        """Invariant comptable : CNAM + patient = net total."""
        req = _insured_request(drugs=[_drug(unit_price="333", quantity=7)])
        result = engine.process(req)
        assert result.cnam_coverage_xof + result.patient_due_xof == result.net_total_xof

    def test_insurance_id_required_for_insured(self) -> None:
        with pytest.raises(ValidationError, match="CNAM"):
            BillingRequest(
                patient_type=PatientType.INSURED,
                insurance_id=None,
                diagnoses=[_diagnosis()],
                drugs=[_drug()],
            )

    def test_no_discount_for_insured(self, engine: BillingEngine) -> None:
        """Les remises programmes ne s'appliquent pas aux assurés."""
        req = _insured_request(
            discount_program=DiscountProgram.GENERIC_SUBSTITUTION,
            drugs=[_drug(is_generic=True)],
        )
        result = engine.process(req)
        assert result.discount_amount_xof == Decimal("0")
        assert result.net_total_xof == result.gross_total_xof

    def test_primary_diagnosis_picked(self, engine: BillingEngine) -> None:
        req = BillingRequest(
            patient_type=PatientType.INSURED,
            insurance_id="CNAM-CI-2026-000001",
            diagnoses=[
                _diagnosis("J06.9", is_primary=False),
                _diagnosis("B54", is_primary=True),
            ],
            drugs=[_drug()],
        )
        result = engine.process(req)
        assert result.primary_diagnosis_cim10 == "B54"

    def test_per_line_cnam_split(self, engine: BillingEngine) -> None:
        """Chaque ligne doit porter sa part CNAM + patient summing to discounted_total."""
        req = _insured_request(
            drugs=[
                _drug(unit_price="500", quantity=4),
                _drug(dci="AMOXICILLIN", unit_price="250", quantity=8),
            ],
        )
        result = engine.process(req)
        for line in result.drug_lines:
            assert line.cnam_part_xof + line.patient_part_xof == line.discounted_total_xof

    def test_multi_drug_gross_total(self, engine: BillingEngine) -> None:
        req = _insured_request(
            drugs=[
                _drug(unit_price="500", quantity=4),  # 2 000
                _drug(dci="AMOXICILLIN", unit_price="250", quantity=8),  # 2 000
            ]
        )
        result = engine.process(req)
        assert result.gross_total_xof == Decimal("4000")


# ===========================================================================
# 4. Patient NON-ASSURÉ — tarification + remises
# ===========================================================================


class TestUninsuredBilling:
    def test_no_discount_full_price(self, engine: BillingEngine) -> None:
        """Sans programme, le patient paye le plein tarif."""
        req = _uninsured_request()
        result = engine.process(req)

        assert result.cnam_coverage_xof == Decimal("0")
        assert result.patient_due_xof == result.net_total_xof
        assert result.discount_amount_xof == Decimal("0")

    def test_generic_substitution_applies_to_generics_only(self, engine: BillingEngine) -> None:
        """GENERIC_SUBSTITUTION : -20 % sur les génériques, 0 sur les originaux."""
        req = _uninsured_request(
            discount_program=DiscountProgram.GENERIC_SUBSTITUTION,
            drugs=[
                _drug(unit_price="1000", quantity=1, is_generic=True),  # 1000 → 800
                _drug(
                    dci="AMOXICILLIN", unit_price="1000", quantity=1, is_generic=False
                ),  # 1000 → 1000
            ],
        )
        result = engine.process(req)
        generic_line = result.drug_lines[0]
        original_line = result.drug_lines[1]

        assert generic_line.discount_rate == Decimal("0.20")
        assert generic_line.discounted_total_xof == Decimal("800")
        assert original_line.discount_rate == Decimal("0")
        assert original_line.discounted_total_xof == Decimal("1000")
        assert result.net_total_xof == Decimal("1800")
        assert result.discount_amount_xof == Decimal("200")

    def test_social_aid_applies_to_all_lines(self, engine: BillingEngine) -> None:
        """-30 % SOCIAL_AID s'applique à toutes les lignes, génériques ou non."""
        req = _uninsured_request(
            discount_program=DiscountProgram.SOCIAL_AID,
            drugs=[
                _drug(unit_price="1000", quantity=1, is_generic=False),
                _drug(dci="AMOXICILLIN", unit_price="1000", quantity=1, is_generic=True),
            ],
        )
        result = engine.process(req)
        for line in result.drug_lines:
            assert line.discount_rate == Decimal("0.30")
            assert line.discounted_total_xof == Decimal("700")
        assert result.net_total_xof == Decimal("1400")

    def test_bulk_generic_applies_to_generics_only(self, engine: BillingEngine) -> None:
        """BULK_GENERIC : -15 % sur génériques uniquement."""
        req = _uninsured_request(
            discount_program=DiscountProgram.BULK_GENERIC,
            drugs=[_drug(unit_price="2000", quantity=1, is_generic=True)],
        )
        result = engine.process(req)
        assert result.drug_lines[0].discounted_total_xof == Decimal("1700")

    def test_uninsured_has_no_cnam(self, engine: BillingEngine) -> None:
        req = _uninsured_request(discount_program=DiscountProgram.SOCIAL_AID)
        result = engine.process(req)
        assert result.cnam_coverage_xof == Decimal("0")
        assert result.insurance_id is None


# ===========================================================================
# 5. Plan de paiement fractionné (BNPL)
# ===========================================================================


class TestInstallmentPlan:
    def test_bnpl_3_months(self, engine: BillingEngine) -> None:
        """6 000 XOF / 3 mois = 2 000 XOF/mois."""
        req = _insured_request(
            payment_method=PaymentMethod.BNPL,
            installment_months=3,
        )
        result = engine.process(req)
        plan = result.installment_plan
        assert plan is not None
        assert plan.months == 3
        assert plan.monthly_amount_xof == Decimal("2000")
        assert plan.first_payment_xof + plan.monthly_amount_xof * 2 == plan.total_xof

    def test_bnpl_rounding_absorbed_in_first_payment(self, engine: BillingEngine) -> None:
        """1 000 XOF / 3 mois : 333 + 333 + 334 (arrondi absorbé en premier versement)."""
        req = _uninsured_request(
            drugs=[_drug(unit_price="1000", quantity=1)],
            payment_method=PaymentMethod.BNPL,
            installment_months=3,
        )
        result = engine.process(req)
        plan = result.installment_plan
        assert plan is not None
        # total = monthly * (months-1) + first_payment
        assert plan.first_payment_xof + plan.monthly_amount_xof * 2 == Decimal("1000")

    def test_no_plan_for_non_bnpl(self, engine: BillingEngine) -> None:
        req = _insured_request(payment_method=PaymentMethod.CASH)
        result = engine.process(req)
        assert result.installment_plan is None

    def test_bnpl_requires_min_2_months(self) -> None:
        with pytest.raises(ValidationError, match="2 mensualités"):
            BillingRequest(
                patient_type=PatientType.UNINSURED,
                diagnoses=[_diagnosis()],
                drugs=[_drug()],
                payment_method=PaymentMethod.BNPL,
                installment_months=1,
            )


# ===========================================================================
# 6. Rapport CMM — OMS/MSF
# ===========================================================================


class TestCMMReport:
    def _make_request(self, entries: list[dict]) -> CMMReportRequest:
        return CMMReportRequest(entries=entries)

    def test_basic_cmm_calculation(self, engine: BillingEngine) -> None:
        req = self._make_request(
            [
                {"dci_code": "ARTEMETHER-LUMEFANTRINE", "cmm_units": 120, "current_stock": 80},
            ]
        )
        report = engine.compute_cmm_report(req)
        entry = report[0]
        # months_of_stock = 80 / 120 ≈ 0.67 → rupture imminente
        assert entry.months_of_stock == pytest.approx(0.67, abs=0.01)
        assert entry.reorder_needed is True
        # suggested = 6 * 120 - 80 = 640
        assert entry.suggested_order_qty == 640

    def test_no_reorder_when_stock_adequate(self, engine: BillingEngine) -> None:
        req = self._make_request(
            [
                {"dci_code": "AMOXICILLIN", "cmm_units": 50, "current_stock": 300},
            ]
        )
        report = engine.compute_cmm_report(req)
        assert report[0].reorder_needed is False
        assert report[0].months_of_stock == 6.0

    def test_reorder_threshold_is_2_months(self, engine: BillingEngine) -> None:
        """Stock exactement = 2 × CMM : limite, pas de commande suggérée."""
        req = self._make_request(
            [
                {"dci_code": "METFORMIN", "cmm_units": 100, "current_stock": 200},
            ]
        )
        report = engine.compute_cmm_report(req)
        assert report[0].months_of_stock == 2.0
        assert report[0].reorder_needed is False

    def test_sorting_critical_first(self, engine: BillingEngine) -> None:
        """Les ruptures imminentes apparaissent en premier dans le rapport."""
        req = self._make_request(
            [
                {"dci_code": "AMOXICILLIN", "cmm_units": 50, "current_stock": 500},  # 10 mois OK
                {
                    "dci_code": "ARTEMETHER-LUMEFANTRINE",
                    "cmm_units": 100,
                    "current_stock": 50,
                },  # 0.5 mois CRITIQUE
                {
                    "dci_code": "PARACETAMOL",
                    "cmm_units": 200,
                    "current_stock": 100,
                },  # 0.5 mois CRITIQUE
            ]
        )
        report = engine.compute_cmm_report(req)
        assert report[0].reorder_needed is True
        assert report[-1].reorder_needed is False

    def test_zero_cmm_no_division_error(self, engine: BillingEngine) -> None:
        """CMM = 0 ne doit pas lever de ZeroDivisionError."""
        req = self._make_request(
            [
                {"dci_code": "OBSOLETE-DRUG", "cmm_units": 0, "current_stock": 10},
            ]
        )
        report = engine.compute_cmm_report(req)
        assert report[0].months_of_stock == 0.0
        assert report[0].suggested_order_qty == 0

    def test_dci_code_uppercased(self, engine: BillingEngine) -> None:
        req = self._make_request(
            [
                {"dci_code": "artemether-lumefantrine", "cmm_units": 10, "current_stock": 5},
            ]
        )
        report = engine.compute_cmm_report(req)
        assert report[0].dci_code == "ARTEMETHER-LUMEFANTRINE"


# ===========================================================================
# 7. Validation de la requête (guards Pydantic)
# ===========================================================================


class TestRequestValidation:
    def test_at_least_one_diagnosis_required(self) -> None:
        with pytest.raises(ValidationError):
            BillingRequest(
                patient_type=PatientType.UNINSURED,
                diagnoses=[],
                drugs=[_drug()],
            )

    def test_at_least_one_drug_required(self) -> None:
        with pytest.raises(ValidationError):
            BillingRequest(
                patient_type=PatientType.UNINSURED,
                diagnoses=[_diagnosis()],
                drugs=[],
            )

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DrugLineRequest(
                dci=DCICode(code="AMOXICILLIN"),
                quantity=-1,
                unit_price_xof=Decimal("500"),
            )

    def test_zero_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DrugLineRequest(
                dci=DCICode(code="AMOXICILLIN"),
                quantity=1,
                unit_price_xof=Decimal("0"),
            )

    def test_regulatory_constants(self) -> None:
        """Les constantes réglementaires sont conformes au décret CMU-CI."""
        assert TAUX_CNAM == Decimal("0.70")
        assert TICKET_MODERATEUR == Decimal("0.30")
        assert TAUX_CNAM + TICKET_MODERATEUR == Decimal("1")
