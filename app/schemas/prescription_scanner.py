"""
Schémas — PrescriptionScanner CMU Côte d'Ivoire
================================================

Validation réglementaire d'ordonnance :
  - Codes CIM-10 (pathologie) et DCI (médicament) obligatoires
  - Détection d'interactions médicamenteuses (CONTRAINDICATED → MINOR)
  - Contre-indications patient (âge, sexe, grossesse, insuffisance rénale/hépatique)
  - Vérification dosage et durée de traitement
  - Traçabilité : score de confiance, signataire, QR-code
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.schemas.billing import CIM10Code, DCICode

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InteractionSeverity(StrEnum):
    """Gravité d'une interaction médicamenteuse (classification OMS/ANSM)."""

    CONTRAINDICATED = "CONTRAINDICATED"  # Association formellement contre-indiquée
    MAJOR = "MAJOR"  # Risque vital — éviter sauf bénéfice > risque
    MODERATE = "MODERATE"  # Surveillance clinique renforcée requise
    MINOR = "MINOR"  # Interaction faible, information patient suffisante


class ContraindicationCategory(StrEnum):
    """Catégorie de contre-indication liée au profil patient."""

    AGE_PEDIATRIC = "AGE_PEDIATRIC"  # Médicament contre-indiqué chez l'enfant
    AGE_GERIATRIC = "AGE_GERIATRIC"  # Adapation posologique sénior
    PREGNANCY = "PREGNANCY"  # Tératogène ou fœtotoxique
    RENAL_IMPAIRMENT = "RENAL_IMPAIRMENT"  # Élimination rénale compromise
    HEPATIC_IMPAIRMENT = "HEPATIC_IMPAIRMENT"  # Métabolisme hépatique compromis
    G6PD_DEFICIENCY = "G6PD_DEFICIENCY"  # Déficit G6PD (fréquent en CI — ~25 %)


class ScanStatus(StrEnum):
    """Statut global de validation de l'ordonnance."""

    VALID = "VALID"  # Ordonnance valide, aucune alerte critique
    WARNING = "WARNING"  # Alertes modérées — dispensation possible avec vigilance
    BLOCKED = "BLOCKED"  # Contre-indication formelle — dispensation interdite


class PatientSex(StrEnum):
    M = "M"
    F = "F"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Profil patient
# ---------------------------------------------------------------------------


class PatientProfile(BaseModel):
    """Contexte clinique du patient pour la validation."""

    age_years: Annotated[float, Field(ge=0, le=120, description="Âge en années")]
    sex: PatientSex = PatientSex.UNKNOWN
    is_pregnant: bool = False
    has_renal_impairment: bool = False
    has_hepatic_impairment: bool = False
    has_g6pd_deficiency: bool = False
    weight_kg: float | None = Field(default=None, gt=0, le=300)

    @model_validator(mode="after")
    def pregnancy_requires_female(self) -> PatientProfile:
        if self.is_pregnant and self.sex == PatientSex.M:
            raise ValueError("is_pregnant=True incompatible avec sex=M.")
        return self


# ---------------------------------------------------------------------------
# Ligne de prescription
# ---------------------------------------------------------------------------


class PrescriptionLine(BaseModel):
    """Un médicament dans l'ordonnance."""

    dci: DCICode
    dose_mg: Annotated[
        float | None,
        Field(default=None, gt=0, description="Dose unitaire en mg"),
    ] = None
    frequency_per_day: Annotated[
        int | None,
        Field(default=None, ge=1, le=24, description="Nombre de prises par jour"),
    ] = None
    duration_days: Annotated[
        int | None,
        Field(default=None, ge=1, le=365, description="Durée du traitement en jours"),
    ] = None
    route: str | None = Field(
        default=None,
        description="Voie d'administration (oral, IV, IM, topique…)",
    )
    is_generic: bool = False

    @property
    def daily_dose_mg(self) -> float | None:
        if self.dose_mg and self.frequency_per_day:
            return self.dose_mg * self.frequency_per_day
        return None


# ---------------------------------------------------------------------------
# Requête de scan
# ---------------------------------------------------------------------------


class PrescriptionRequest(BaseModel):
    """Ordonnance complète soumise au scanner."""

    diagnoses: Annotated[
        list[CIM10Code],
        Field(min_length=1, description="Diagnostics CIM-10 (obligatoires CMU)"),
    ]
    drugs: Annotated[
        list[PrescriptionLine],
        Field(min_length=1, description="Médicaments DCI (obligatoires CMU)"),
    ]
    patient: PatientProfile
    prescriber_id: str | None = Field(
        default=None,
        description="Identifiant du prescripteur (numéro ONMCI ou INSP)",
    )
    prescription_date: date | None = None
    qr_code_token: str | None = Field(
        default=None,
        description="Token QR-code pour vérification d'authenticité",
    )

    @model_validator(mode="after")
    def date_not_in_future(self) -> PrescriptionRequest:
        if self.prescription_date and self.prescription_date > date.today():
            raise ValueError("La date de prescription ne peut pas être dans le futur.")
        return self


# ---------------------------------------------------------------------------
# Résultats du scanner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrugInteractionFlag:
    """Interaction détectée entre deux médicaments."""

    drug_a: str
    drug_b: str
    severity: InteractionSeverity
    mechanism: str  # Mécanisme pharmacologique
    clinical_consequence: str  # Conséquence clinique
    management: str  # Conduite à tenir


@dataclass(frozen=True)
class ContraindicationFlag:
    """Contre-indication liée au profil patient."""

    dci_code: str
    category: ContraindicationCategory
    description: str
    management: str


@dataclass(frozen=True)
class DosageFlag:
    """Alerte posologique (surdosage, sous-dosage, durée excessive)."""

    dci_code: str
    issue: str
    details: str
    recommendation: str


class ScanResult(BaseModel):
    """Résultat complet du scan d'ordonnance."""

    status: ScanStatus
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Score de confiance global (1.0 = ordonnance parfaitement conforme)",
    )

    # Alertes détectées
    interactions: list[DrugInteractionFlag] = Field(default_factory=list)
    contraindications: list[ContraindicationFlag] = Field(default_factory=list)
    dosage_flags: list[DosageFlag] = Field(default_factory=list)

    # Synthèse
    blocked_drugs: list[str] = Field(
        default_factory=list,
        description="DCI dont la dispensation est bloquée (CONTRAINDICATED)",
    )
    warning_drugs: list[str] = Field(
        default_factory=list,
        description="DCI nécessitant une vigilance accrue",
    )

    # Authenticité
    qr_verified: bool = False
    regulatory_note: str = "Scan conforme CMU Côte d'Ivoire — CIM-10 & DCI vérifiés"

    # Méta
    scanned_drugs: list[str] = Field(default_factory=list)
    scanned_diagnoses: list[str] = Field(default_factory=list)
    interaction_count: int = 0
    contraindication_count: int = 0
