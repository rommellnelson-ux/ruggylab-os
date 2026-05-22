"""
Moteur de Facturation Hybride CMU — Côte d'Ivoire
==================================================

Réglementation CNAM appliquée :
  - Taux de prise en charge CNAM  : 70 %
  - Ticket Modérateur (patient)   : 30 %
  - Codes CIM-10 et DCI OBLIGATOIRES à chaque facturation

Architecture :
  Python 3.11+ · Programmation Orientée Objet · Dataclasses · Type Hinting
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from app.schemas.billing import (
    BillingRequest,
    BillingResult,
    BillLineResult,
    CMMEntry,
    CMMReportRequest,
    DiscountProgram,
    InstallmentPlan,
    PatientType,
    PaymentMethod,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes réglementaires CMU
# ---------------------------------------------------------------------------

TAUX_CNAM: Final[Decimal] = Decimal("0.70")  # Part prise en charge par la CNAM
TICKET_MODERATEUR: Final[Decimal] = Decimal("0.30")  # Reste à charge du patient assuré

# Taux de remise par programme (non-assurés)
_DISCOUNT_RATES: Final[dict[DiscountProgram, Decimal]] = {
    DiscountProgram.NONE: Decimal("0"),
    DiscountProgram.GENERIC_SUBSTITUTION: Decimal("0.20"),
    DiscountProgram.SOCIAL_AID: Decimal("0.30"),
    DiscountProgram.BULK_GENERIC: Decimal("0.15"),
}

# Arrondi XOF (Franc CFA, 0 décimale)
_XOF_ROUND = Decimal("1")


# ---------------------------------------------------------------------------
# Helpers d'arrondi
# ---------------------------------------------------------------------------


def _round_xof(amount: Decimal) -> Decimal:
    """Arrondi au Franc CFA entier le plus proche (ROUND_HALF_UP)."""
    return amount.quantize(_XOF_ROUND, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Moteur principal
# ---------------------------------------------------------------------------


@dataclass
class BillingEngine:
    """
    Moteur de facturation hybride pour pharmacie CMU-CI.

    Gère simultanément :
      - Patients assurés  → calcul CNAM 70 % / Ticket Modérateur 30 %
      - Patients non-assurés → tarification plein tarif + remises programmes
      - Paiement fractionné BNPL
      - Rapport CMM (Consommation Mensuelle Moyenne) OMS/MSF
    """

    taux_cnam: Decimal = field(default=TAUX_CNAM)
    ticket_moderateur: Decimal = field(default=TICKET_MODERATEUR)

    def __post_init__(self) -> None:
        if self.taux_cnam + self.ticket_moderateur != Decimal("1"):
            raise ValueError(
                f"La somme taux_cnam ({self.taux_cnam}) + ticket_moderateur "
                f"({self.ticket_moderateur}) doit être égale à 1."
            )

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    def process(self, request: BillingRequest) -> BillingResult:
        """
        Calcule une facture complète à partir d'une BillingRequest validée.

        La méthode délègue au sous-moteur assuré ou non-assuré
        selon le statut du patient.
        """
        logger.info(
            "billing.process",
            extra={
                "patient_type": request.patient_type,
                "drug_count": len(request.drugs),
                "diagnosis_count": len(request.diagnoses),
                "payment_method": request.payment_method,
            },
        )

        primary_cim10 = next(
            (d.cim10.code for d in request.diagnoses if d.is_primary),
            request.diagnoses[0].cim10.code,
        )

        if request.patient_type == PatientType.INSURED:
            return self._process_insured(request, primary_cim10)
        return self._process_uninsured(request, primary_cim10)

    # ------------------------------------------------------------------
    # Flux ASSURÉ — CNAM 70 / 30
    # ------------------------------------------------------------------

    def _process_insured(self, request: BillingRequest, primary_cim10: str) -> BillingResult:
        """
        Patient assuré CNAM.

        Règle CMU : CNAM prend en charge 70 % du montant net.
        Le patient règle le Ticket Modérateur (30 %).
        Les remises programmes NE s'appliquent PAS aux assurés
        (la couverture CNAM est le levier principal).
        """
        drug_lines, gross_total = self._compute_lines(
            request,
            discount_rate=Decimal("0"),  # pas de remise programme pour les assurés
        )

        net_total = gross_total  # pas de remise supplémentaire
        cnam_part = _round_xof(net_total * self.taux_cnam)
        patient_part = _round_xof(net_total * self.ticket_moderateur)

        # Correction d'arrondi : le patient paye le reliquat
        if cnam_part + patient_part != net_total:
            patient_part = net_total - cnam_part

        # Mise à jour des lignes avec la répartition CNAM
        drug_lines = self._assign_cnam_split(drug_lines, self.taux_cnam)

        installment = self._make_installment(
            patient_part, request.installment_months, request.payment_method
        )

        return BillingResult(
            patient_type=request.patient_type,
            insurance_id=request.insurance_id,
            primary_diagnosis_cim10=primary_cim10,
            drug_lines=drug_lines,
            gross_total_xof=gross_total,
            discount_amount_xof=Decimal("0"),
            net_total_xof=net_total,
            cnam_coverage_xof=cnam_part,
            patient_due_xof=patient_part,
            payment_method=request.payment_method,
            installment_plan=installment,
            discount_program=DiscountProgram.NONE,
        )

    # ------------------------------------------------------------------
    # Flux NON-ASSURÉ — tarification plein tarif + remises
    # ------------------------------------------------------------------

    def _process_uninsured(self, request: BillingRequest, primary_cim10: str) -> BillingResult:
        """
        Patient non assuré.

        Remises éligibles selon programme :
          - GENERIC_SUBSTITUTION : -20 % sur chaque ligne générique
          - SOCIAL_AID           : -30 % sur l'ensemble du montant
          - BULK_GENERIC         : -15 % sur les lignes génériques
        Le patient paye l'intégralité du montant net (CNAM = 0 XOF).
        """
        discount_rate = _DISCOUNT_RATES[request.discount_program]
        drug_lines, gross_total = self._compute_lines(request, discount_rate)

        net_total = sum((line.discounted_total_xof for line in drug_lines), Decimal("0"))
        discount_amount = gross_total - net_total

        installment = self._make_installment(
            net_total, request.installment_months, request.payment_method
        )

        return BillingResult(
            patient_type=request.patient_type,
            insurance_id=None,
            primary_diagnosis_cim10=primary_cim10,
            drug_lines=drug_lines,
            gross_total_xof=gross_total,
            discount_amount_xof=_round_xof(discount_amount),
            net_total_xof=_round_xof(net_total),
            cnam_coverage_xof=Decimal("0"),
            patient_due_xof=_round_xof(net_total),
            payment_method=request.payment_method,
            installment_plan=installment,
            discount_program=request.discount_program,
        )

    # ------------------------------------------------------------------
    # Calcul des lignes médicaments
    # ------------------------------------------------------------------

    def _compute_lines(
        self, request: BillingRequest, discount_rate: Decimal
    ) -> tuple[list[BillLineResult], Decimal]:
        """
        Calcule chaque ligne médicament et retourne (lignes, total_brut).

        La remise s'applique uniquement aux lignes génériques si le programme
        est GENERIC_SUBSTITUTION ou BULK_GENERIC ; elle s'applique à tous si SOCIAL_AID.
        """
        results: list[BillLineResult] = []
        gross_total = Decimal("0")

        per_line_programs = {
            DiscountProgram.GENERIC_SUBSTITUTION,
            DiscountProgram.BULK_GENERIC,
        }

        for drug in request.drugs:
            line_total = _round_xof(drug.line_total_xof)
            gross_total += line_total

            # Détermination du taux de remise effectif pour cette ligne
            if request.discount_program in per_line_programs:
                effective_rate = discount_rate if drug.is_generic else Decimal("0")
            else:
                effective_rate = discount_rate  # SOCIAL_AID ou NONE s'applique à toutes les lignes

            discounted_total = _round_xof(line_total * (Decimal("1") - effective_rate))

            results.append(
                BillLineResult(
                    dci_code=drug.dci.code,
                    quantity=drug.quantity,
                    unit_price_xof=drug.unit_price_xof,
                    line_total_xof=line_total,
                    discount_rate=effective_rate,
                    discounted_total_xof=discounted_total,
                    # CNAM split sera appliqué si assuré (voir _assign_cnam_split)
                    cnam_part_xof=Decimal("0"),
                    patient_part_xof=discounted_total,
                    is_generic=drug.is_generic,
                )
            )

        return results, _round_xof(gross_total)

    # ------------------------------------------------------------------
    # Répartition CNAM sur les lignes
    # ------------------------------------------------------------------

    @staticmethod
    def _assign_cnam_split(lines: list[BillLineResult], taux_cnam: Decimal) -> list[BillLineResult]:
        """
        Affecte la part CNAM et la part patient à chaque ligne (patient assuré).
        """
        updated: list[BillLineResult] = []
        for line in lines:
            cnam = _round_xof(line.discounted_total_xof * taux_cnam)
            patient = line.discounted_total_xof - cnam  # évite l'erreur d'arrondi cumulée
            updated.append(
                line.model_copy(update={"cnam_part_xof": cnam, "patient_part_xof": patient})
            )
        return updated

    # ------------------------------------------------------------------
    # Plan de paiement fractionné (BNPL)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_installment(
        total: Decimal, months: int, method: PaymentMethod
    ) -> InstallmentPlan | None:
        """Génère un plan BNPL si applicable."""
        if method != PaymentMethod.BNPL or months <= 1:
            return None

        monthly = _round_xof(total / months)
        # Le premier versement absorbe le reliquat d'arrondi
        first = total - monthly * (months - 1)
        return InstallmentPlan(
            total_xof=total,
            months=months,
            monthly_amount_xof=monthly,
            first_payment_xof=_round_xof(first),
        )

    # ------------------------------------------------------------------
    # Rapport CMM (Consommation Mensuelle Moyenne) — OMS/MSF
    # ------------------------------------------------------------------

    @staticmethod
    def compute_cmm_report(request: CMMReportRequest) -> list[CMMEntry]:
        """
        Génère un rapport CMM selon le modèle OMS/MSF.

        Pour chaque médicament :
          - months_of_stock  = stock_actuel / CMM
          - reorder_needed   = True si months_of_stock < 2 mois (seuil OMS)
          - suggested_order  = (CMM × 6 mois) - stock_actuel

        Returns:
            Liste de CMMEntry triée par criticité décroissante
            (les ruptures imminentes en premier).
        """
        entries: list[CMMEntry] = []
        for raw in request.entries:
            entry = CMMEntry(
                dci_code=raw.dci_code,  # already uppercased by CMMEntryRequest validator
                cmm_units=raw.cmm_units,
                current_stock=raw.current_stock,
            )
            entries.append(entry)

        # Tri : ruptures d'abord, puis stock décroissant
        entries.sort(key=lambda e: (not e.reorder_needed, e.months_of_stock))
        return entries


# ---------------------------------------------------------------------------
# Singleton applicatif
# ---------------------------------------------------------------------------

_engine: BillingEngine | None = None


def get_billing_engine() -> BillingEngine:
    """Factory / singleton FastAPI-injectable."""
    global _engine
    if _engine is None:
        _engine = BillingEngine()
    return _engine
