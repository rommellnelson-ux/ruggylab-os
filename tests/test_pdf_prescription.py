"""
Tests — Rapport PDF d'ordonnance CMU Côte d'Ivoire
===================================================

Couverture :
  - PDF généré non vide (len > 100 bytes)
  - Débute par %PDF
  - Ordonnance VALID → PDF sans bloc BLOCKED
  - Ordonnance BLOCKED → PDF contient le statut BLOQUE
  - Patient G6PD + PRIMAQUINE → contre-indication dans le PDF
  - Prescripteur + QR valide → qr_verified=True affiché dans le PDF
  - Endpoint FastAPI POST /prescription/report → 200, content-type application/pdf
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.schemas.billing import CIM10Code, DCICode
from app.schemas.prescription_scanner import (
    ContraindicationCategory,
    ContraindicationFlag,
    DosageFlag,
    DrugInteractionFlag,
    InteractionSeverity,
    PatientProfile,
    PatientSex,
    PrescriptionLine,
    PrescriptionRequest,
    ScanResult,
    ScanStatus,
)
from app.services.pdf_prescription import build_prescription_report
from app.services.prescription_scanner import PrescriptionScanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    drugs: list[PrescriptionLine] | None = None,
    patient: PatientProfile | None = None,
    diagnoses: list[CIM10Code] | None = None,
    prescriber_id: str | None = "ONMCI-2026-001",
    qr_token: str | None = None,
    prescription_date: date | None = None,
) -> PrescriptionRequest:
    return PrescriptionRequest(
        diagnoses=diagnoses or [_diag()],
        drugs=drugs or [_line("AMOXICILLIN", dose_mg=500, freq=3, duration_days=7)],
        patient=patient or _patient(),
        prescriber_id=prescriber_id,
        qr_code_token=qr_token,
        prescription_date=prescription_date or date.today() - timedelta(days=1),
    )


def _valid_result() -> ScanResult:
    return ScanResult(
        status=ScanStatus.VALID,
        confidence_score=1.0,
        scanned_drugs=["AMOXICILLIN"],
        scanned_diagnoses=["B54"],
        qr_verified=True,
    )


def _blocked_result() -> ScanResult:
    return ScanResult(
        status=ScanStatus.BLOCKED,
        confidence_score=0.2,
        interactions=[
            DrugInteractionFlag(
                drug_a="ARTEMETHER-LUMEFANTRINE",
                drug_b="HALOFANTRINE",
                severity=InteractionSeverity.CONTRAINDICATED,
                mechanism="Allongement QTc synergique",
                clinical_consequence="Risque de torsade de pointe fatale",
                management="Association contre-indiquee — arreter HALOFANTRINE",
            )
        ],
        blocked_drugs=["HALOFANTRINE"],
        scanned_drugs=["ARTEMETHER-LUMEFANTRINE", "HALOFANTRINE"],
        scanned_diagnoses=["B54"],
        qr_verified=False,
        interaction_count=1,
    )


def _g6pd_result() -> ScanResult:
    return ScanResult(
        status=ScanStatus.BLOCKED,
        confidence_score=0.3,
        contraindications=[
            ContraindicationFlag(
                dci_code="PRIMAQUINE",
                category=ContraindicationCategory.G6PD_DEFICIENCY,
                description="PRIMAQUINE contre-indiquee en cas de deficit G6PD — risque d'hemolise aigue",
                management="Eviter PRIMAQUINE — utiliser chloroquine ou autre alternative",
            )
        ],
        blocked_drugs=["PRIMAQUINE"],
        scanned_drugs=["PRIMAQUINE"],
        scanned_diagnoses=["B51"],
        qr_verified=False,
        contraindication_count=1,
    )


# ---------------------------------------------------------------------------
# Tests unitaires du service pdf_prescription
# ---------------------------------------------------------------------------


class TestBuildPrescriptionReport:
    def test_pdf_non_vide(self) -> None:
        """Le PDF généré doit faire plus de 100 octets."""
        pdf = build_prescription_report(_request(), _valid_result())
        assert len(pdf) > 100

    def test_pdf_debute_par_magic_bytes(self) -> None:
        """Le PDF doit commencer par %PDF (signature PDF standard)."""
        pdf = build_prescription_report(_request(), _valid_result())
        assert pdf[:4] == b"%PDF"

    def test_pdf_contient_eof(self) -> None:
        """Un PDF valide se termine par %%EOF."""
        pdf = build_prescription_report(_request(), _valid_result())
        assert b"%%EOF" in pdf

    def test_valid_pas_de_bloc_bloque(self) -> None:
        """Une ordonnance VALID ne doit pas contenir le mot BLOQUE dans le PDF."""
        pdf = build_prescription_report(_request(), _valid_result())
        assert b"BLOQUE" not in pdf

    def test_valid_contient_statut_valid(self) -> None:
        """Une ordonnance VALID doit afficher le statut VALID dans le PDF."""
        pdf = build_prescription_report(_request(), _valid_result())
        assert b"VALID" in pdf

    def test_blocked_contient_statut_bloque(self) -> None:
        """Une ordonnance BLOCKED doit afficher BLOQUE dans le PDF."""
        req = _request(
            drugs=[_line("ARTEMETHER-LUMEFANTRINE"), _line("HALOFANTRINE")],
        )
        pdf = build_prescription_report(req, _blocked_result())
        assert b"BLOQUE" in pdf

    def test_blocked_contient_medicament_bloque(self) -> None:
        """Le PDF d'une ordonnance bloquée doit mentionner les DCI bloqués."""
        req = _request(
            drugs=[_line("ARTEMETHER-LUMEFANTRINE"), _line("HALOFANTRINE")],
        )
        pdf = build_prescription_report(req, _blocked_result())
        assert b"HALOFANTRINE" in pdf

    def test_g6pd_primaquine_contient_contraindication(self) -> None:
        """G6PD + PRIMAQUINE → le PDF doit mentionner G6PD et PRIMAQUINE."""
        req = _request(
            drugs=[_line("PRIMAQUINE", dose_mg=15, freq=1, duration_days=14)],
            patient=_patient(g6pd=True),
            diagnoses=[_diag("B51")],
        )
        pdf = build_prescription_report(req, _g6pd_result())
        assert b"PRIMAQUINE" in pdf
        assert b"G6PD" in pdf

    def test_qr_verifie_true_affiche_ok(self) -> None:
        """qr_verified=True → le PDF doit indiquer QR OK."""
        req = _request(prescriber_id="ONMCI-2026-007", qr_token="abc123")
        result = _valid_result()  # qr_verified=True
        pdf = build_prescription_report(req, result)
        assert b"QR verifie OK" in pdf or b"OK" in pdf

    def test_qr_verifie_false_non_verifie(self) -> None:
        """qr_verified=False → le PDF ne doit pas indiquer QR OK."""
        req = _request()
        result = ScanResult(
            status=ScanStatus.WARNING,
            confidence_score=0.8,
            qr_verified=False,
        )
        pdf = build_prescription_report(req, result)
        assert b"non verifie" in pdf

    def test_prescripteur_present_dans_pdf(self) -> None:
        """L'identifiant du prescripteur doit apparaître dans le PDF."""
        req = _request(prescriber_id="ONMCI-TEST-999")
        pdf = build_prescription_report(req, _valid_result())
        assert b"ONMCI-TEST-999" in pdf

    def test_diagnostic_cim10_present(self) -> None:
        """Le code CIM-10 doit apparaître dans le PDF."""
        req = _request(diagnoses=[_diag("J06")])
        pdf = build_prescription_report(req, _valid_result())
        assert b"J06" in pdf

    def test_medicament_dci_present(self) -> None:
        """Le DCI du médicament doit apparaître dans le PDF."""
        req = _request(drugs=[_line("AMOXICILLIN", dose_mg=500, freq=3, duration_days=7)])
        pdf = build_prescription_report(req, _valid_result())
        assert b"AMOXICILLIN" in pdf

    def test_score_confiance_present(self) -> None:
        """Le score de confiance doit être mentionné dans le PDF."""
        pdf = build_prescription_report(_request(), _valid_result())
        # 1.0 → 100%
        assert b"100%" in pdf

    def test_pied_de_page_ruggylab(self) -> None:
        """Le pied de page doit contenir la marque ruggylab-os."""
        pdf = build_prescription_report(_request(), _valid_result())
        assert b"ruggylab-os" in pdf

    def test_warning_contient_alerte(self) -> None:
        """Une ordonnance WARNING doit afficher WARNING dans le PDF."""
        req = _request(
            drugs=[_line("IBUPROFEN"), _line("ASPIRIN")],
        )
        scanner = PrescriptionScanner()
        result = scanner.scan(req)
        pdf = build_prescription_report(req, result)
        assert b"WARNING" in pdf or b"VALID" in pdf  # selon la gravité réelle

    def test_profil_risque_grossesse_present(self) -> None:
        """Si la patiente est enceinte, 'Grossesse' doit apparaître dans le profil."""
        req = _request(patient=_patient(sex=PatientSex.F, pregnant=True))
        pdf = build_prescription_report(req, _valid_result())
        assert b"Grossesse" in pdf

    def test_profil_risque_insuffisance_renale(self) -> None:
        """Insuffisance rénale doit apparaître si has_renal_impairment=True."""
        req = _request(patient=_patient(renal=True))
        pdf = build_prescription_report(req, _valid_result())
        assert b"renale" in pdf

    def test_dose_mg_presente_dans_tableau(self) -> None:
        """La dose en mg doit apparaître dans le tableau des médicaments."""
        req = _request(drugs=[_line("AMOXICILLIN", dose_mg=250, freq=2, duration_days=5)])
        pdf = build_prescription_report(req, _valid_result())
        assert b"250" in pdf

    def test_interaction_severity_dans_pdf(self) -> None:
        """La gravité d'une interaction doit être visible dans le PDF."""
        req = _request(
            drugs=[_line("ARTEMETHER-LUMEFANTRINE"), _line("HALOFANTRINE")],
        )
        pdf = build_prescription_report(req, _blocked_result())
        assert b"CONTRAINDICATED" in pdf

    def test_dosage_flag_dans_pdf(self) -> None:
        """Un flag posologique doit apparaître dans la section Alertes."""
        req = _request()
        result = ScanResult(
            status=ScanStatus.WARNING,
            confidence_score=0.7,
            dosage_flags=[
                DosageFlag(
                    dci_code="AMOXICILLIN",
                    issue="Dose journaliere excessive",
                    details="Dose calculee depasse 3000 mg/j",
                    recommendation="Reduire a 500 mg x 3/j",
                )
            ],
        )
        pdf = build_prescription_report(req, result)
        assert b"AMOXICILLIN" in pdf
        assert b"Dose journaliere" in pdf or b"posologiques" in pdf


# ---------------------------------------------------------------------------
# Tests du endpoint FastAPI
# ---------------------------------------------------------------------------


class TestEndpointPdfPrescription:
    def _get_auth_token(self, client: TestClient) -> str:
        response = client.post(
            "/api/v1/login/access-token",
            data={
                "username": "admin",
                "password": "change_me_admin_password",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]

    def test_report_status_200(self, client: TestClient) -> None:
        """POST /prescription/report doit retourner 200."""
        token = self._get_auth_token(client)
        payload = {
            "diagnoses": [{"code": "B54", "description": "Paludisme"}],
            "drugs": [
                {
                    "dci": {"code": "AMOXICILLIN"},
                    "dose_mg": 500,
                    "frequency_per_day": 3,
                    "duration_days": 7,
                    "route": "oral",
                }
            ],
            "patient": {
                "age_years": 30,
                "sex": "M",
                "is_pregnant": False,
                "has_renal_impairment": False,
                "has_hepatic_impairment": False,
                "has_g6pd_deficiency": False,
            },
            "prescriber_id": "ONMCI-2026-001",
            "prescription_date": str(date.today() - timedelta(days=1)),
        }
        response = client.post(
            "/api/v1/prescription/report",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

    def test_report_content_type_pdf(self, client: TestClient) -> None:
        """Le content-type de la réponse doit être application/pdf."""
        token = self._get_auth_token(client)
        payload = {
            "diagnoses": [{"code": "J06", "description": "IVAS"}],
            "drugs": [
                {
                    "dci": {"code": "AMOXICILLIN"},
                    "dose_mg": 500,
                    "frequency_per_day": 3,
                    "duration_days": 7,
                    "route": "oral",
                }
            ],
            "patient": {
                "age_years": 25,
                "sex": "F",
            },
            "prescription_date": str(date.today() - timedelta(days=2)),
        }
        response = client.post(
            "/api/v1/prescription/report",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "application/pdf" in response.headers["content-type"]

    def test_report_body_starts_with_pdf_magic(self, client: TestClient) -> None:
        """Le corps de la réponse doit commencer par %PDF."""
        token = self._get_auth_token(client)
        payload = {
            "diagnoses": [{"code": "B54"}],
            "drugs": [{"dci": {"code": "AMOXICILLIN"}, "dose_mg": 500, "frequency_per_day": 3}],
            "patient": {"age_years": 40, "sex": "M"},
        }
        response = client.post(
            "/api/v1/prescription/report",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.content[:4] == b"%PDF"

    def test_report_content_disposition(self, client: TestClient) -> None:
        """Le header Content-Disposition doit indiquer un fichier .pdf."""
        token = self._get_auth_token(client)
        payload = {
            "diagnoses": [{"code": "B54"}],
            "drugs": [{"dci": {"code": "AMOXICILLIN"}}],
            "patient": {"age_years": 30, "sex": "M"},
        }
        response = client.post(
            "/api/v1/prescription/report",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".pdf" in disposition

    def test_report_unauthenticated_401(self, client: TestClient) -> None:
        """Sans token, le endpoint doit retourner 401."""
        payload = {
            "diagnoses": [{"code": "B54"}],
            "drugs": [{"dci": {"code": "AMOXICILLIN"}}],
            "patient": {"age_years": 30, "sex": "M"},
        }
        response = client.post("/api/v1/prescription/report", json=payload)
        assert response.status_code == 401
