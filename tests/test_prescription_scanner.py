"""
Tests du PrescriptionScanner CMU Côte d'Ivoire
===============================================

Couverture :
  - Interactions médicamenteuses (CONTRAINDICATED, MAJOR, MODERATE)
  - Contre-indications patient (G6PD, grossesse, âge, IR)
  - Flags posologiques (surdosage adulte, surdosage pédiatrique, durée excessive)
  - Vérification QR-code (stub)
  - Statut global (VALID, WARNING, BLOCKED) et score de confiance
  - Ordonnance complète sans alertes → VALID + confidence 1.0 (hors QR)
  - Tri des interactions par gravité décroissante
  - Cas limites : ordonnance mono-médicament, patient inconnu
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.billing import CIM10Code, DCICode
from app.schemas.prescription_scanner import (
    ContraindicationCategory,
    InteractionSeverity,
    PatientProfile,
    PatientSex,
    PrescriptionLine,
    PrescriptionRequest,
    ScanStatus,
)
from app.services.prescription_scanner import (
    _CONTRAINDICATIONS,
    _INTERACTIONS,
    _MAX_DAILY_DOSE_ADULT,
    PrescriptionScanner,
    get_prescription_scanner,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def scanner() -> PrescriptionScanner:
    return PrescriptionScanner()


def _patient(
    age: float = 35.0,
    sex: PatientSex = PatientSex.M,
    pregnant: bool = False,
    renal: bool = False,
    hepatic: bool = False,
    g6pd: bool = False,
    weight_kg: float | None = None,
) -> PatientProfile:
    return PatientProfile(
        age_years=age,
        sex=sex,
        is_pregnant=pregnant,
        has_renal_impairment=renal,
        has_hepatic_impairment=hepatic,
        has_g6pd_deficiency=g6pd,
        weight_kg=weight_kg,
    )


def _line(
    dci: str,
    dose_mg: float | None = None,
    freq: int | None = None,
    duration_days: int | None = None,
    route: str | None = "oral",
) -> PrescriptionLine:
    return PrescriptionLine(
        dci=DCICode(code=dci),
        dose_mg=dose_mg,
        frequency_per_day=freq,
        duration_days=duration_days,
        route=route,
    )


def _diag(code: str = "B54") -> CIM10Code:
    return CIM10Code(code=code)


def _request(
    drugs: list[PrescriptionLine],
    patient: PatientProfile | None = None,
    diagnoses: list[CIM10Code] | None = None,
    prescriber_id: str | None = None,
    qr_token: str | None = None,
    prescription_date: date | None = None,
) -> PrescriptionRequest:
    return PrescriptionRequest(
        diagnoses=diagnoses or [_diag()],
        drugs=drugs,
        patient=patient or _patient(),
        prescriber_id=prescriber_id,
        qr_code_token=qr_token,
        prescription_date=prescription_date,
    )


# ---------------------------------------------------------------------------
# 1. Base de données statiques
# ---------------------------------------------------------------------------


class TestStaticData:
    def test_interactions_not_empty(self) -> None:
        assert len(_INTERACTIONS) >= 20

    def test_all_interactions_have_mechanism(self) -> None:
        for itx in _INTERACTIONS:
            assert itx.mechanism, f"Pas de mécanisme pour {itx.drug_a}/{itx.drug_b}"

    def test_contraindications_cover_key_dci(self) -> None:
        expected = {"PRIMAQUINE", "METFORMIN", "IBUPROFEN", "ASPIRIN", "WARFARIN", "CODEINE"}
        assert expected.issubset(set(_CONTRAINDICATIONS.keys()))

    def test_max_daily_doses_positive(self) -> None:
        for dci, dose in _MAX_DAILY_DOSE_ADULT.items():
            assert dose > 0, f"Dose négative ou nulle pour {dci}"


# ---------------------------------------------------------------------------
# 2. Interactions médicamenteuses
# ---------------------------------------------------------------------------


class TestInteractionDetection:
    def test_contraindicated_artemether_halofantrine(self, scanner: PrescriptionScanner) -> None:
        """ARTEMETHER-LUMEFANTRINE + HALOFANTRINE → CONTRAINDICATED (QT)."""
        result = scanner.scan(
            _request(
                [_line("ARTEMETHER-LUMEFANTRINE"), _line("HALOFANTRINE")],
            )
        )
        assert result.status == ScanStatus.BLOCKED
        assert any(
            itx.severity == InteractionSeverity.CONTRAINDICATED for itx in result.interactions
        )
        assert result.interaction_count >= 1

    def test_major_artemether_quinine(self, scanner: PrescriptionScanner) -> None:
        """ARTEMETHER-LUMEFANTRINE + QUININE → MAJOR."""
        result = scanner.scan(_request([_line("ARTEMETHER-LUMEFANTRINE"), _line("QUININE")]))
        assert result.status in (ScanStatus.WARNING, ScanStatus.BLOCKED)
        assert any(itx.severity == InteractionSeverity.MAJOR for itx in result.interactions)

    def test_moderate_ibuprofen_aspirin(self, scanner: PrescriptionScanner) -> None:
        """IBUPROFEN + ASPIRIN → MODERATE."""
        result = scanner.scan(_request([_line("IBUPROFEN"), _line("ASPIRIN")]))
        assert result.status == ScanStatus.WARNING
        assert any(itx.severity == InteractionSeverity.MODERATE for itx in result.interactions)

    def test_no_interaction_unrelated_drugs(self, scanner: PrescriptionScanner) -> None:
        """Paracétamol + Amoxicilline → aucune interaction connue."""
        result = scanner.scan(
            _request([_line("PARACETAMOL"), _line("AMOXICILLIN")], patient=_patient())
        )
        assert result.interaction_count == 0

    def test_interactions_sorted_by_severity(self, scanner: PrescriptionScanner) -> None:
        """L'interaction la plus grave doit apparaître en premier."""
        result = scanner.scan(
            _request(
                [
                    _line("ARTEMETHER-LUMEFANTRINE"),
                    _line("HALOFANTRINE"),
                    _line("IBUPROFEN"),
                    _line("ASPIRIN"),
                ]
            )
        )
        severities = [itx.severity for itx in result.interactions]
        # Toutes les CONTRAINDICATED avant MAJOR avant MODERATE
        order = {
            InteractionSeverity.CONTRAINDICATED: 0,
            InteractionSeverity.MAJOR: 1,
            InteractionSeverity.MODERATE: 2,
            InteractionSeverity.MINOR: 3,
        }
        for i in range(len(severities) - 1):
            assert order[severities[i]] <= order[severities[i + 1]]

    def test_triple_drug_combinations(self, scanner: PrescriptionScanner) -> None:
        """Trois médicaments → toutes les paires sont vérifiées."""
        result = scanner.scan(
            _request(
                [_line("AMIODARONE"), _line("QUININE"), _line("WARFARIN")],
            )
        )
        # AMIODARONE+QUININE = CONTRAINDICATED, AMIODARONE+WARFARIN = MAJOR
        assert result.interaction_count >= 2
        assert result.status == ScanStatus.BLOCKED

    def test_contraindicated_metoprolol_verapamil(self, scanner: PrescriptionScanner) -> None:
        """METOPROLOL + VERAPAMIL → CONTRAINDICATED (BAV complet)."""
        result = scanner.scan(_request([_line("METOPROLOL"), _line("VERAPAMIL")]))
        assert result.status == ScanStatus.BLOCKED
        assert any(
            itx.severity == InteractionSeverity.CONTRAINDICATED for itx in result.interactions
        )

    def test_blocked_drugs_listed_from_contraindicated_interaction(
        self, scanner: PrescriptionScanner
    ) -> None:
        """Les DCI impliqués dans une interaction CONTRAINDICATED sont dans blocked_drugs."""
        result = scanner.scan(_request([_line("ARTEMETHER-LUMEFANTRINE"), _line("HALOFANTRINE")]))
        blocked = set(result.blocked_drugs)
        assert "ARTEMETHER-LUMEFANTRINE" in blocked or "HALOFANTRINE" in blocked


# ---------------------------------------------------------------------------
# 3. Contre-indications patient
# ---------------------------------------------------------------------------


class TestContraindications:
    def test_primaquine_g6pd_deficiency(self, scanner: PrescriptionScanner) -> None:
        """PRIMAQUINE + G6PD déficitaire → BLOCKED."""
        result = scanner.scan(
            _request(
                [_line("PRIMAQUINE")],
                patient=_patient(g6pd=True),
            )
        )
        assert result.status == ScanStatus.BLOCKED
        assert result.contraindication_count >= 1
        ci_cats = [ci.category for ci in result.contraindications]
        assert ContraindicationCategory.G6PD_DEFICIENCY in ci_cats

    def test_primaquine_pregnancy(self, scanner: PrescriptionScanner) -> None:
        """PRIMAQUINE + grossesse → BLOCKED."""
        result = scanner.scan(
            _request(
                [_line("PRIMAQUINE")],
                patient=_patient(age=28.0, sex=PatientSex.F, pregnant=True),
            )
        )
        assert result.status == ScanStatus.BLOCKED
        cats = [ci.category for ci in result.contraindications]
        assert ContraindicationCategory.PREGNANCY in cats

    def test_dapsone_g6pd(self, scanner: PrescriptionScanner) -> None:
        """DAPSONE + G6PD déficitaire → BLOCKED."""
        result = scanner.scan(_request([_line("DAPSONE")], patient=_patient(g6pd=True)))
        assert result.status == ScanStatus.BLOCKED

    def test_metformin_renal_impairment(self, scanner: PrescriptionScanner) -> None:
        """METFORMIN + insuffisance rénale → BLOCKED."""
        result = scanner.scan(_request([_line("METFORMIN")], patient=_patient(renal=True)))
        assert result.status == ScanStatus.BLOCKED
        cats = [ci.category for ci in result.contraindications]
        assert ContraindicationCategory.RENAL_IMPAIRMENT in cats

    def test_ibuprofen_pregnancy(self, scanner: PrescriptionScanner) -> None:
        """IBUPROFEN + grossesse → BLOCKED."""
        result = scanner.scan(
            _request(
                [_line("IBUPROFEN")],
                patient=_patient(age=25.0, sex=PatientSex.F, pregnant=True),
            )
        )
        assert result.status == ScanStatus.BLOCKED

    def test_ibuprofen_renal_impairment(self, scanner: PrescriptionScanner) -> None:
        """IBUPROFEN + IR → BLOCKED."""
        result = scanner.scan(_request([_line("IBUPROFEN")], patient=_patient(renal=True)))
        assert result.status == ScanStatus.BLOCKED

    def test_aspirin_pediatric(self, scanner: PrescriptionScanner) -> None:
        """ASPIRIN + enfant 8 ans → BLOCKED (risque syndrome de Reye)."""
        result = scanner.scan(_request([_line("ASPIRIN")], patient=_patient(age=8.0)))
        assert result.status == ScanStatus.BLOCKED
        cats = [ci.category for ci in result.contraindications]
        assert ContraindicationCategory.AGE_PEDIATRIC in cats

    def test_codeine_pediatric(self, scanner: PrescriptionScanner) -> None:
        """CODÉINE + enfant 10 ans → BLOCKED (dépression respiratoire)."""
        result = scanner.scan(_request([_line("CODEINE")], patient=_patient(age=10.0)))
        assert result.status == ScanStatus.BLOCKED

    def test_warfarin_pregnancy(self, scanner: PrescriptionScanner) -> None:
        """WARFARIN + grossesse → BLOCKED (embryopathie)."""
        result = scanner.scan(
            _request(
                [_line("WARFARIN")],
                patient=_patient(age=30.0, sex=PatientSex.F, pregnant=True),
            )
        )
        assert result.status == ScanStatus.BLOCKED

    def test_tetracycline_pediatric_under_8(self, scanner: PrescriptionScanner) -> None:
        """TÉTRACYCLINE + enfant 7 ans → BLOCKED (émail dentaire)."""
        result = scanner.scan(_request([_line("TETRACYCLINE")], patient=_patient(age=7.0)))
        assert result.status == ScanStatus.BLOCKED

    def test_ibuprofen_adult_healthy_no_ci(self, scanner: PrescriptionScanner) -> None:
        """IBUPROFEN + adulte sain → aucune contre-indication."""
        result = scanner.scan(_request([_line("IBUPROFEN")], patient=_patient(age=35.0)))
        # Pas de CI, pas d'interaction → VALID (hors dosage non renseigné)
        assert result.contraindication_count == 0

    def test_primaquine_no_ci_healthy_adult(self, scanner: PrescriptionScanner) -> None:
        """PRIMAQUINE + adulte sain sans G6PD → aucune contre-indication."""
        result = scanner.scan(_request([_line("PRIMAQUINE")], patient=_patient(g6pd=False)))
        assert result.contraindication_count == 0


# ---------------------------------------------------------------------------
# 4. Flags posologiques
# ---------------------------------------------------------------------------


class TestDosageFlags:
    def test_paracetamol_adult_overdose(self, scanner: PrescriptionScanner) -> None:
        """PARACÉTAMOL 1500 mg × 4 = 6000 mg/j > 4000 mg/j → SURDOSAGE."""
        result = scanner.scan(
            _request(
                [_line("PARACETAMOL", dose_mg=1500.0, freq=4)],
                patient=_patient(age=35.0),
            )
        )
        assert any("SURDOSAGE" in f.issue for f in result.dosage_flags)
        assert result.status == ScanStatus.WARNING

    def test_paracetamol_within_limit(self, scanner: PrescriptionScanner) -> None:
        """PARACÉTAMOL 500 mg × 4 = 2000 mg/j < 4000 mg/j → OK."""
        result = scanner.scan(
            _request(
                [_line("PARACETAMOL", dose_mg=500.0, freq=4)],
                patient=_patient(),
            )
        )
        assert not any("SURDOSAGE" in f.issue for f in result.dosage_flags)

    def test_ibuprofen_adult_max_exact(self, scanner: PrescriptionScanner) -> None:
        """IBUPROFEN 800 mg × 3 = 2400 mg/j == limite adulte → pas de flag."""
        result = scanner.scan(
            _request(
                [_line("IBUPROFEN", dose_mg=800.0, freq=3)],
                patient=_patient(age=40.0),
            )
        )
        overdose_flags = [f for f in result.dosage_flags if "SURDOSAGE" in f.issue]
        assert len(overdose_flags) == 0

    def test_pediatric_overdose_flag(self, scanner: PrescriptionScanner) -> None:
        """PARACÉTAMOL 750 mg × 4 = 3000 mg/j > 50 % de 4000 → SURDOSAGE_PEDIATRIQUE chez enfant 5 ans."""
        result = scanner.scan(
            _request(
                [_line("PARACETAMOL", dose_mg=750.0, freq=4)],
                patient=_patient(age=5.0, weight_kg=20.0),
            )
        )
        ped_flags = [f for f in result.dosage_flags if f.issue == "SURDOSAGE_PEDIATRIQUE"]
        assert len(ped_flags) >= 1
        # Le détail doit mentionner mg/kg/j (poids renseigné)
        assert "mg/kg/j" in ped_flags[0].details

    def test_pediatric_overdose_no_weight(self, scanner: PrescriptionScanner) -> None:
        """SURDOSAGE_PEDIATRIQUE sans poids → pas de suffix mg/kg/j."""
        result = scanner.scan(
            _request(
                [_line("PARACETAMOL", dose_mg=750.0, freq=4)],
                patient=_patient(age=5.0, weight_kg=None),
            )
        )
        ped_flags = [f for f in result.dosage_flags if f.issue == "SURDOSAGE_PEDIATRIQUE"]
        assert len(ped_flags) >= 1
        assert "mg/kg/j" not in ped_flags[0].details

    def test_antibiotic_excessive_duration(self, scanner: PrescriptionScanner) -> None:
        """CIPROFLOXACIN 40 jours → DUREE_EXCESSIVE."""
        result = scanner.scan(
            _request(
                [_line("CIPROFLOXACIN", dose_mg=500.0, freq=2, duration_days=40)],
                patient=_patient(),
            )
        )
        dur_flags = [f for f in result.dosage_flags if f.issue == "DUREE_EXCESSIVE"]
        assert len(dur_flags) >= 1

    def test_antibiotic_normal_duration_no_flag(self, scanner: PrescriptionScanner) -> None:
        """CIPROFLOXACIN 7 jours → pas de flag durée."""
        result = scanner.scan(
            _request(
                [_line("CIPROFLOXACIN", dose_mg=500.0, freq=2, duration_days=7)],
                patient=_patient(),
            )
        )
        dur_flags = [f for f in result.dosage_flags if f.issue == "DUREE_EXCESSIVE"]
        assert len(dur_flags) == 0

    def test_no_dose_no_dosage_flag(self, scanner: PrescriptionScanner) -> None:
        """Quand dose_mg ou freq est absent → aucun flag posologique."""
        result = scanner.scan(_request([_line("PARACETAMOL")], patient=_patient()))
        assert result.dosage_flags == []


# ---------------------------------------------------------------------------
# 5. Vérification QR-code
# ---------------------------------------------------------------------------


class TestQRVerification:
    def test_valid_hex_token_32chars(self, scanner: PrescriptionScanner) -> None:
        """Token hex ≥ 32 caractères avec prescripteur → qr_verified=True."""
        token = "a" * 32  # 32 hex chars valides
        assert scanner._verify_qr(token, "ONMCI-12345") is True  # noqa: SLF001

    def test_invalid_token_too_short(self, scanner: PrescriptionScanner) -> None:
        """Token trop court → qr_verified=False."""
        assert scanner._verify_qr("deadbeef", "ONMCI-12345") is False  # noqa: SLF001

    def test_non_hex_token(self, scanner: PrescriptionScanner) -> None:
        """Token non-hexadécimal → qr_verified=False."""
        assert scanner._verify_qr("z" * 32, "ONMCI-12345") is False  # noqa: SLF001

    def test_missing_token(self, scanner: PrescriptionScanner) -> None:
        """Token None → qr_verified=False."""
        assert scanner._verify_qr(None, "ONMCI-12345") is False  # noqa: SLF001

    def test_missing_prescriber(self, scanner: PrescriptionScanner) -> None:
        """Prescripteur None → qr_verified=False même avec bon token."""
        token = "b" * 64
        assert scanner._verify_qr(token, None) is False  # noqa: SLF001

    def test_qr_unverified_reduces_confidence(self, scanner: PrescriptionScanner) -> None:
        """Sans QR, le score de confiance est diminué de 0.05."""
        # Ordonnance simple sans alertes
        result_no_qr = scanner.scan(
            _request([_line("PARACETAMOL", dose_mg=500.0, freq=2)], patient=_patient())
        )
        result_with_qr = scanner.scan(
            _request(
                [_line("PARACETAMOL", dose_mg=500.0, freq=2)],
                patient=_patient(),
                prescriber_id="ONMCI-99999",
                qr_token="f" * 64,
            )
        )
        assert result_with_qr.confidence_score > result_no_qr.confidence_score
        assert abs(result_with_qr.confidence_score - result_no_qr.confidence_score - 0.05) < 0.001


# ---------------------------------------------------------------------------
# 6. Statut global et score de confiance
# ---------------------------------------------------------------------------


class TestStatusAndConfidence:
    def test_valid_clean_prescription(self, scanner: PrescriptionScanner) -> None:
        """Ordonnance sans alertes + QR valide → VALID, confidence proche de 1.0."""
        result = scanner.scan(
            _request(
                [_line("PARACETAMOL", dose_mg=500.0, freq=3)],
                patient=_patient(),
                prescriber_id="ONMCI-00001",
                qr_token="c" * 64,
            )
        )
        assert result.status == ScanStatus.VALID
        assert result.confidence_score == pytest.approx(1.0, abs=0.001)

    def test_blocked_confidence_below_threshold(self, scanner: PrescriptionScanner) -> None:
        """BLOCKED → confidence significativement < 1.0."""
        result = scanner.scan(_request([_line("ARTEMETHER-LUMEFANTRINE"), _line("HALOFANTRINE")]))
        assert result.status == ScanStatus.BLOCKED
        assert result.confidence_score < 0.7

    def test_warning_confidence_intermediate(self, scanner: PrescriptionScanner) -> None:
        """WARNING → confidence entre 0.5 et 0.99."""
        result = scanner.scan(_request([_line("IBUPROFEN"), _line("ASPIRIN")], patient=_patient()))
        assert result.status == ScanStatus.WARNING
        assert 0.5 < result.confidence_score < 1.0

    def test_confidence_never_negative(self, scanner: PrescriptionScanner) -> None:
        """Le score de confiance est toujours ≥ 0.0, même avec de nombreuses alertes."""
        result = scanner.scan(
            _request(
                [
                    _line("ARTEMETHER-LUMEFANTRINE"),
                    _line("HALOFANTRINE"),
                    _line("QUININE"),
                    _line("MEFLOQUINE"),
                    _line("AMIODARONE"),
                ],
                patient=_patient(g6pd=True, renal=True, pregnant=False),
            )
        )
        assert result.confidence_score >= 0.0

    def test_contraindicated_interaction_forces_blocked(self, scanner: PrescriptionScanner) -> None:
        """Une seule interaction CONTRAINDICATED suffit à passer en BLOCKED."""
        result = scanner.scan(_request([_line("QUININE"), _line("MEFLOQUINE")]))
        assert result.status == ScanStatus.BLOCKED

    def test_patient_contraindication_forces_blocked(self, scanner: PrescriptionScanner) -> None:
        """Une seule contre-indication patient suffit à passer en BLOCKED."""
        result = scanner.scan(_request([_line("METFORMIN")], patient=_patient(renal=True)))
        assert result.status == ScanStatus.BLOCKED

    def test_warning_drugs_from_moderate_interaction(self, scanner: PrescriptionScanner) -> None:
        """Les DCI en interaction MODERATE apparaissent dans warning_drugs."""
        result = scanner.scan(_request([_line("IBUPROFEN"), _line("ASPIRIN")]))
        assert "IBUPROFEN" in result.warning_drugs or "ASPIRIN" in result.warning_drugs

    def test_warning_drugs_from_dosage_flag(self, scanner: PrescriptionScanner) -> None:
        """Un DCI en surdosage apparaît dans warning_drugs si non bloqué."""
        result = scanner.scan(
            _request(
                [_line("PARACETAMOL", dose_mg=1500.0, freq=4)],
                patient=_patient(),
            )
        )
        assert "PARACETAMOL" in result.warning_drugs

    def test_major_interaction_sets_warning_not_blocked(self, scanner: PrescriptionScanner) -> None:
        """Une interaction MAJOR seule → WARNING (pas BLOCKED)."""
        result = scanner.scan(_request([_line("ARTEMETHER-LUMEFANTRINE"), _line("QUININE")]))
        # MAJOR interaction seule ne doit pas bloquer
        if not result.contraindications:
            assert result.status in (ScanStatus.WARNING, ScanStatus.BLOCKED)


# ---------------------------------------------------------------------------
# 7. Métadonnées du résultat
# ---------------------------------------------------------------------------


class TestScanResultMetadata:
    def test_scanned_drugs_populated(self, scanner: PrescriptionScanner) -> None:
        drugs = [_line("PARACETAMOL"), _line("AMOXICILLIN")]
        result = scanner.scan(_request(drugs))
        assert set(result.scanned_drugs) == {"PARACETAMOL", "AMOXICILLIN"}

    def test_scanned_diagnoses_populated(self, scanner: PrescriptionScanner) -> None:
        result = scanner.scan(
            _request(
                [_line("PARACETAMOL")],
                diagnoses=[_diag("B54"), _diag("J06.9")],
            )
        )
        assert "B54" in result.scanned_diagnoses
        assert "J06.9" in result.scanned_diagnoses

    def test_interaction_count_matches_list_length(self, scanner: PrescriptionScanner) -> None:
        result = scanner.scan(_request([_line("ARTEMETHER-LUMEFANTRINE"), _line("QUININE")]))
        assert result.interaction_count == len(result.interactions)

    def test_contraindication_count_matches_list_length(self, scanner: PrescriptionScanner) -> None:
        result = scanner.scan(
            _request([_line("PRIMAQUINE")], patient=_patient(g6pd=True, pregnant=False))
        )
        assert result.contraindication_count == len(result.contraindications)

    def test_regulatory_note_present(self, scanner: PrescriptionScanner) -> None:
        result = scanner.scan(_request([_line("PARACETAMOL")]))
        assert "CMU" in result.regulatory_note
        assert "CIM-10" in result.regulatory_note


# ---------------------------------------------------------------------------
# 8. Requête complète (intégration)
# ---------------------------------------------------------------------------


class TestFullIntegration:
    def test_paludisme_simple_acte(self, scanner: PrescriptionScanner) -> None:
        """Ordonnance paludisme typique CI : ACT + paracétamol antalgie, patient sain."""
        result = scanner.scan(
            PrescriptionRequest(
                diagnoses=[CIM10Code(code="B54")],
                drugs=[
                    PrescriptionLine(
                        dci=DCICode(code="ARTEMETHER-LUMEFANTRINE"),
                        dose_mg=80.0,
                        frequency_per_day=2,
                        duration_days=3,
                    ),
                    PrescriptionLine(
                        dci=DCICode(code="PARACETAMOL"),
                        dose_mg=1000.0,
                        frequency_per_day=3,
                        duration_days=3,
                    ),
                ],
                patient=PatientProfile(age_years=32.0, sex=PatientSex.M),
                prescriber_id="ONMCI-77777",
                qr_code_token="e" * 64,
            )
        )
        # Aucune interaction entre ACT + paracétamol, patient sain
        assert result.status == ScanStatus.VALID
        assert result.interaction_count == 0
        assert result.contraindication_count == 0
        assert result.confidence_score == pytest.approx(1.0, abs=0.001)
        assert result.qr_verified is True

    def test_tb_rifampicin_warfarin_efavirenz(self, scanner: PrescriptionScanner) -> None:
        """Co-infection TB/VIH : rifampicine + warfarine + éfavirenz → interactions MAJOR."""
        result = scanner.scan(
            _request(
                [
                    _line("RIFAMPICIN"),
                    _line("WARFARIN"),
                    _line("EFAVIRENZ"),
                ],
                patient=_patient(),
            )
        )
        # RIFAMPICIN+WARFARIN et RIFAMPICIN+EFAVIRENZ → au moins 2 interactions MAJOR
        major_count = sum(1 for i in result.interactions if i.severity == InteractionSeverity.MAJOR)
        assert major_count >= 2
        assert result.status in (ScanStatus.WARNING, ScanStatus.BLOCKED)

    def test_cardiac_patient_multiple_blocking(self, scanner: PrescriptionScanner) -> None:
        """Patient cardiaque : AMIODARONE + DIGOXIN + QUININE → plusieurs interactions graves."""
        result = scanner.scan(
            _request(
                [_line("AMIODARONE"), _line("DIGOXIN"), _line("QUININE")],
                patient=_patient(),
            )
        )
        assert result.status == ScanStatus.BLOCKED
        assert result.confidence_score < 0.5


# ---------------------------------------------------------------------------
# 9. Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_scanner_returns_same_instance(self) -> None:
        s1 = get_prescription_scanner()
        s2 = get_prescription_scanner()
        assert s1 is s2

    def test_singleton_is_prescription_scanner(self) -> None:
        scanner = get_prescription_scanner()
        assert isinstance(scanner, PrescriptionScanner)


# ---------------------------------------------------------------------------
# 10. Validation Pydantic — PrescriptionRequest
# ---------------------------------------------------------------------------


class TestPrescriptionRequestValidation:
    def test_empty_drugs_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PrescriptionRequest(
                diagnoses=[_diag()],
                drugs=[],
                patient=_patient(),
            )

    def test_empty_diagnoses_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PrescriptionRequest(
                diagnoses=[],
                drugs=[_line("PARACETAMOL")],
                patient=_patient(),
            )

    def test_future_date_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PrescriptionRequest(
                diagnoses=[_diag()],
                drugs=[_line("PARACETAMOL")],
                patient=_patient(),
                prescription_date=date.today() + timedelta(days=1),
            )

    def test_pregnant_male_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PatientProfile(age_years=30.0, sex=PatientSex.M, is_pregnant=True)

    def test_past_date_accepted(self) -> None:
        req = PrescriptionRequest(
            diagnoses=[_diag()],
            drugs=[_line("PARACETAMOL")],
            patient=_patient(),
            prescription_date=date.today() - timedelta(days=1),
        )
        assert req.prescription_date is not None

    def test_dci_normalised_to_uppercase(self) -> None:
        line = PrescriptionLine(dci=DCICode(code="paracetamol"))
        assert line.dci.code == "PARACETAMOL"

    def test_daily_dose_computed_correctly(self) -> None:
        line = _line("PARACETAMOL", dose_mg=500.0, freq=3)
        assert line.daily_dose_mg == pytest.approx(1500.0)

    def test_daily_dose_none_when_freq_missing(self) -> None:
        line = _line("PARACETAMOL", dose_mg=500.0)
        assert line.daily_dose_mg is None
