"""
Schémas Pydantic pour le moteur de facturation CMU Côte d'Ivoire.

Réglementation :
  - Taux CNAM  : 70 % (part assurance)
  - Ticket Modérateur : 30 % (reste à charge patient assuré)
  - Codes CIM-10 (pathologie) et DCI (médicament) obligatoires
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PatientType(StrEnum):
    """Statut de couverture du patient."""

    INSURED = "INSURED"  # Assuré CNAM / mutuelle
    UNINSURED = "UNINSURED"  # Patient non assuré


class PaymentMethod(StrEnum):
    """Modalité de règlement."""

    CASH = "CASH"
    MOBILE_MONEY = "MOBILE_MONEY"
    INSURANCE = "INSURANCE"
    BNPL = "BNPL"  # Buy Now Pay Later / micro-crédit santé


class DiscountProgram(StrEnum):
    """Programmes de réduction applicables aux non-assurés."""

    NONE = "NONE"
    GENERIC_SUBSTITUTION = "GENERIC_SUBSTITUTION"  # -20 % sur molécule générique
    SOCIAL_AID = "SOCIAL_AID"  # Programme d'aide sociale -30 %
    BULK_GENERIC = "BULK_GENERIC"  # Achat groupé molécules -15 %


# ---------------------------------------------------------------------------
# Primitives métier
# ---------------------------------------------------------------------------

# Regex CIM-10 : lettre + 2 chiffres optionnellement suivi d'un point et 1-3 chars
_CIM10_RE = re.compile(r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,3})?$")
# DCI : code alphanumérique normalisé OMS (au moins 3 caractères)
_DCI_RE = re.compile(r"^[A-Z0-9\-]{3,50}$")


class CIM10Code(BaseModel):
    """Code de pathologie selon la Classification Internationale des Maladies (10e révision)."""

    code: Annotated[str, Field(min_length=3, max_length=8, examples=["B54", "J06.9"])]
    description: str = ""

    @field_validator("code")
    @classmethod
    def validate_format(cls, v: str) -> str:
        v = v.strip().upper()
        if not _CIM10_RE.match(v):
            raise ValueError(
                f"Code CIM-10 invalide : '{v}'. "
                "Format attendu : lettre + 2 chiffres [+ point + 1-3 caractères] "
                "(ex. B54, J06.9, Z29.11)"
            )
        return v


class DCICode(BaseModel):
    """Dénomination Commune Internationale d'un médicament (OMS)."""

    code: Annotated[
        str, Field(min_length=3, max_length=50, examples=["AMOXICILLIN", "ARTEMETHER-LUMEFANTRINE"])
    ]
    description: str = ""

    @field_validator("code")
    @classmethod
    def validate_format(cls, v: str) -> str:
        v = v.strip().upper()
        if not _DCI_RE.match(v):
            raise ValueError(
                f"Code DCI invalide : '{v}'. "
                "Format attendu : alphanumérique OMS (ex. AMOXICILLIN, ARTEMETHER-LUMEFANTRINE)"
            )
        return v


# ---------------------------------------------------------------------------
# Lignes de facturation
# ---------------------------------------------------------------------------


class DrugLineRequest(BaseModel):
    """Ligne médicament d'une ordonnance."""

    dci: DCICode = Field(description="Dénomination Commune Internationale (obligatoire CMU)")
    quantity: Annotated[int, Field(gt=0, le=9999, description="Nombre d'unités dispensées")]
    unit_price_xof: Annotated[
        Decimal,
        Field(gt=Decimal("0"), description="Prix unitaire en Francs CFA (XOF)"),
    ]
    is_generic: bool = Field(
        default=False,
        description="Vrai si la molécule est un générique (éligible réduction)",
    )
    cmm_units: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Consommation Mensuelle Moyenne en unités (modèle OMS/MSF)",
        ),
    ] = None

    @property
    def line_total_xof(self) -> Decimal:
        return self.unit_price_xof * self.quantity


class DiagnosisLineRequest(BaseModel):
    """Diagnostic associé à la facturation (CIM-10 obligatoire)."""

    cim10: CIM10Code = Field(description="Code CIM-10 de la pathologie (obligatoire CMU)")
    is_primary: bool = Field(default=True, description="Diagnostic principal (True) ou secondaire")


# ---------------------------------------------------------------------------
# Requête de facturation
# ---------------------------------------------------------------------------


class BillingRequest(BaseModel):
    """Corps de la requête de calcul de facture."""

    patient_type: PatientType
    insurance_id: str | None = Field(
        default=None,
        description="Numéro d'affiliation CNAM (obligatoire si patient assuré)",
        examples=["CNAM-CI-2026-001234"],
    )
    diagnoses: list[DiagnosisLineRequest] = Field(
        min_length=1,
        description="Au moins un diagnostic CIM-10 est obligatoire",
    )
    drugs: list[DrugLineRequest] = Field(
        min_length=1,
        description="Au moins un médicament DCI est obligatoire",
    )
    payment_method: PaymentMethod = PaymentMethod.CASH
    discount_program: DiscountProgram = DiscountProgram.NONE
    installment_months: Annotated[
        int,
        Field(default=1, ge=1, le=12, description="Nombre de mensualités (BNPL)"),
    ] = 1

    @model_validator(mode="after")
    def check_insurance_id_required(self) -> BillingRequest:
        if self.patient_type == PatientType.INSURED and not self.insurance_id:
            raise ValueError("Le numéro d'affiliation CNAM est obligatoire pour un patient assuré.")
        return self

    @model_validator(mode="after")
    def check_bnpl_consistency(self) -> BillingRequest:
        if self.payment_method == PaymentMethod.BNPL and self.installment_months < 2:
            raise ValueError("Le paiement fractionné (BNPL) nécessite au moins 2 mensualités.")
        return self


# ---------------------------------------------------------------------------
# Résultats de facturation
# ---------------------------------------------------------------------------


class BillLineResult(BaseModel):
    """Détail calculé pour une ligne médicament."""

    dci_code: str
    quantity: int
    unit_price_xof: Decimal
    line_total_xof: Decimal
    discount_rate: Decimal = Decimal("0")
    discounted_total_xof: Decimal
    cnam_part_xof: Decimal
    patient_part_xof: Decimal
    is_generic: bool


class InstallmentPlan(BaseModel):
    """Plan de paiement fractionné (BNPL)."""

    total_xof: Decimal
    months: int
    monthly_amount_xof: Decimal
    first_payment_xof: Decimal  # peut différer si arrondi


class BillingResult(BaseModel):
    """Résultat complet du calcul de facturation."""

    patient_type: PatientType
    insurance_id: str | None
    primary_diagnosis_cim10: str
    drug_lines: list[BillLineResult]

    # Totaux bruts
    gross_total_xof: Decimal = Field(description="Total avant remises")
    discount_amount_xof: Decimal = Field(description="Montant total des remises appliquées")
    net_total_xof: Decimal = Field(description="Total après remises")

    # Répartition CMU
    cnam_coverage_xof: Decimal = Field(description="Part prise en charge CNAM (70 %)")
    patient_due_xof: Decimal = Field(description="Reste à charge patient (30 % ticket modérateur)")

    # Paiement
    payment_method: PaymentMethod
    installment_plan: InstallmentPlan | None = None

    # Méta
    discount_program: DiscountProgram
    regulatory_note: str = (
        "Facturation conforme CMU Côte d'Ivoire — Taux CNAM 70 % / Ticket Modérateur 30 %"
    )


# ---------------------------------------------------------------------------
# Rapport CMM (Consommation Mensuelle Moyenne)
# ---------------------------------------------------------------------------


@dataclass
class CMMEntry:
    """Entrée CMM pour un médicament selon le modèle OMS/MSF."""

    dci_code: str
    cmm_units: int  # consommation mensuelle moyenne
    current_stock: int
    months_of_stock: float = field(init=False)
    reorder_needed: bool = field(init=False)
    suggested_order_qty: int = field(init=False)

    # Paramètres OMS/MSF
    SAFETY_STOCK_MONTHS: float = 2.0  # stock de sécurité : 2 mois
    ORDER_UP_TO_MONTHS: float = 6.0  # niveau cible : 6 mois

    def __post_init__(self) -> None:
        self.months_of_stock = (
            round(self.current_stock / self.cmm_units, 2) if self.cmm_units > 0 else 0.0
        )
        self.reorder_needed = self.months_of_stock < self.SAFETY_STOCK_MONTHS
        target = int(self.cmm_units * self.ORDER_UP_TO_MONTHS)
        self.suggested_order_qty = max(0, target - self.current_stock)


class CMMReportRequest(BaseModel):
    """Requête de rapport CMM (tableau de bord stock)."""

    entries: list[dict[str, int]] = Field(
        description="Liste de {dci_code, cmm_units, current_stock}",
        examples=[[{"dci_code": "ARTEMETHER-LUMEFANTRINE", "cmm_units": 120, "current_stock": 80}]],
    )
