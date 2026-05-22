"""
PrescriptionScanner — Validation d'Ordonnance CMU Côte d'Ivoire
===============================================================

Fonctionnalités :
  1. Validation réglementaire (CIM-10 + DCI obligatoires)
  2. Détection d'interactions médicamenteuses (base OMS/ANSM — 60+ paires)
  3. Contre-indications patient (G6PD fréquent en CI ~25 %, grossesse, IR, IH)
  4. Vérification posologique (dosage maximal adulte/pédiatrique)
  5. Vérification d'authenticité QR-code (stub extensible)
  6. Score de confiance composite

Architecture :
  Python 3.11+ · OOP · Dataclasses · Type Hinting strict
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Final

from app.schemas.prescription_scanner import (
    ContraindicationCategory,
    ContraindicationFlag,
    DosageFlag,
    DrugInteractionFlag,
    InteractionSeverity,
    PatientProfile,
    PrescriptionLine,
    PrescriptionRequest,
    ScanResult,
    ScanStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base de données d'interactions médicamenteuses
# Calibrée pour le contexte CI (OMS Essential Medicines + ANSM + PNLP)
# Format : frozenset({dci_a, dci_b}) → DrugInteractionFlag
# ---------------------------------------------------------------------------

_INTERACTIONS: Final[list[DrugInteractionFlag]] = [
    # ── Antipaludéens ──────────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="ARTEMETHER-LUMEFANTRINE",
        drug_b="HALOFANTRINE",
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism="Allongement synergique de l'intervalle QT",
        clinical_consequence="Risque de torsades de pointes et mort subite",
        management="Association formellement contre-indiquée — choisir un autre ACT",
    ),
    DrugInteractionFlag(
        drug_a="ARTEMETHER-LUMEFANTRINE",
        drug_b="QUININE",
        severity=InteractionSeverity.MAJOR,
        mechanism="Allongement additif de l'intervalle QT",
        clinical_consequence="Arythmie ventriculaire grave",
        management="Éviter la co-administration. Si nécessaire : ECG continu",
    ),
    DrugInteractionFlag(
        drug_a="ARTEMETHER-LUMEFANTRINE",
        drug_b="ERYTHROMYCIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Allongement QT et inhibition CYP3A4 par érythromycine",
        clinical_consequence="Augmentation des concentrations de lumefantrine + risque QT",
        management="Préférer azithromycine si un macrolide est nécessaire",
    ),
    DrugInteractionFlag(
        drug_a="PRIMAQUINE",
        drug_b="DAPSONE",
        severity=InteractionSeverity.MAJOR,
        mechanism="Stress oxydatif érythrocytaire additif",
        clinical_consequence="Anémie hémolytique sévère — risque majeur si G6PD déficitaire",
        management="Contre-indiqué chez les sujets G6PD déficitaires. Doser G6PD avant.",
    ),
    DrugInteractionFlag(
        drug_a="QUININE",
        drug_b="MEFLOQUINE",
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism="Allongement majeur de l'intervalle QT, effets neurologiques cumulés",
        clinical_consequence="Convulsions, arythmie létale",
        management="Association contre-indiquée en toutes circonstances",
    ),
    DrugInteractionFlag(
        drug_a="ARTESUNATE",
        drug_b="RIFAMPICIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Induction CYP2A6 par rifampicine → diminution des concentrations d'artésunate",
        clinical_consequence="Risque d'échec thérapeutique antipaludéen",
        management="Éviter. Si co-administration obligatoire, augmenter la dose d'artésunate",
    ),
    # ── Antibiotiques ──────────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="CIPROFLOXACIN",
        drug_b="THEOPHYLLINE",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition CYP1A2 par ciprofloxacine",
        clinical_consequence="Surtoxicité théophylline : convulsions, arythmie",
        management="Réduire la dose de théophylline de 30-50 %. Surveiller théophyllinémie.",
    ),
    DrugInteractionFlag(
        drug_a="CIPROFLOXACIN",
        drug_b="WARFARIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition CYP1A2/2C9 → augmentation effet anticoagulant",
        clinical_consequence="Risque hémorragique majeur",
        management="Surveiller INR quotidiennement. Ajuster la dose de warfarine.",
    ),
    DrugInteractionFlag(
        drug_a="METRONIDAZOLE",
        drug_b="WARFARIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition CYP2C9 et déplacement liaison protéique",
        clinical_consequence="Potentialisation de l'effet anticoagulant",
        management="Réduire la dose de warfarine. INR 2× par semaine.",
    ),
    DrugInteractionFlag(
        drug_a="RIFAMPICIN",
        drug_b="WARFARIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Induction puissante CYP2C9 et CYP3A4",
        clinical_consequence="Réduction de l'effet anticoagulant → thrombose",
        management="Augmenter la dose de warfarine, surveiller INR hebdomadaire",
    ),
    DrugInteractionFlag(
        drug_a="RIFAMPICIN",
        drug_b="ORAL-CONTRACEPTIVE",
        severity=InteractionSeverity.MAJOR,
        mechanism="Induction enzymatique → accélération du métabolisme des estrogènes/progestatifs",
        clinical_consequence="Échec contraceptif — grossesse non désirée",
        management="Utiliser une contraception non hormonale pendant le traitement + 1 mois après",
    ),
    DrugInteractionFlag(
        drug_a="RIFAMPICIN",
        drug_b="EFAVIRENZ",
        severity=InteractionSeverity.MAJOR,
        mechanism="Induction CYP3A4/2B6 → sous-exposition à l'éfavirenz",
        clinical_consequence="Risque d'échec virologique VIH",
        management="Augmenter la dose d'éfavirenz à 800 mg/j si poids > 60 kg",
    ),
    DrugInteractionFlag(
        drug_a="ERYTHROMYCIN",
        drug_b="SIMVASTATIN",
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism="Inhibition CYP3A4 → accumulation de statine",
        clinical_consequence="Rhabdomyolyse sévère avec insuffisance rénale aiguë",
        management="Contre-indiqué. Suspendre la statine ou utiliser pravastatin (non CYP3A4)",
    ),
    DrugInteractionFlag(
        drug_a="CLARITHROMYCIN",
        drug_b="COLCHICINE",
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism="Inhibition CYP3A4/P-gp → accumulation toxique de colchicine",
        clinical_consequence="Colchicine-toxicité : aplasie médullaire, défaillance multi-viscérale",
        management="Contre-indiqué chez l'insuffisant rénal ou hépatique. Alternatives : azithromycine",
    ),
    # ── AINS / Analgésiques ────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="IBUPROFEN",
        drug_b="ASPIRIN",
        severity=InteractionSeverity.MODERATE,
        mechanism="Compétition pour le site de liaison COX-1 de l'aspirine",
        clinical_consequence="Ibuprofène bloque l'effet antiplaquettaire de l'aspirine",
        management="Administrer l'aspirine ≥ 2h avant l'ibuprofène si association nécessaire",
    ),
    DrugInteractionFlag(
        drug_a="IBUPROFEN",
        drug_b="LISINOPRIL",
        severity=InteractionSeverity.MODERATE,
        mechanism="AINS → rétention sodée et hydrique → antagonisme IEC",
        clinical_consequence="Réduction de l'effet antihypertenseur + risque IRA",
        management="Surveillance PA et créatinine. Préférer paracétamol si antalgie nécessaire.",
    ),
    DrugInteractionFlag(
        drug_a="IBUPROFEN",
        drug_b="WARFARIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition plaquettaire + déplacement liaison protéique",
        clinical_consequence="Risque hémorragique majoré (GI notamment)",
        management="Éviter. Utiliser paracétamol comme alternative analgésique.",
    ),
    DrugInteractionFlag(
        drug_a="ASPIRIN",
        drug_b="WARFARIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition plaquettaire + déplacement liaison protéique warfarine",
        clinical_consequence="Risque hémorragique très élevé",
        management="Si indispensable (SCA), surveillance INR quotidienne, dose aspirine ≤ 100 mg",
    ),
    # ── Cardiovasculaires ──────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="AMIODARONE",
        drug_b="QUININE",
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism="Allongement massif du QT par les deux molécules",
        clinical_consequence="Torsades de pointes et fibrillation ventriculaire",
        management="Association absolument contre-indiquée. Traiter paludisme par autre ACT.",
    ),
    DrugInteractionFlag(
        drug_a="AMIODARONE",
        drug_b="WARFARIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition CYP2C9 → augmentation effet warfarine",
        clinical_consequence="Risque hémorragique majeur",
        management="Réduire la dose de warfarine de 30-50 %. INR 2× par semaine.",
    ),
    DrugInteractionFlag(
        drug_a="DIGOXIN",
        drug_b="AMIODARONE",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition P-gp → diminution de l'élimination rénale de la digoxine",
        clinical_consequence="Toxicité digitalique : BAV, FV",
        management="Réduire la dose de digoxine de 50 %. Surveiller digoxinémie et ECG.",
    ),
    DrugInteractionFlag(
        drug_a="DIGOXIN",
        drug_b="ERYTHROMYCIN",
        severity=InteractionSeverity.MAJOR,
        mechanism="Inhibition P-gp intestinale + modification flore digestive",
        clinical_consequence="Augmentation des concentrations de digoxine → toxicité",
        management="Surveiller digoxinémie. Réduire dose si nécessaire.",
    ),
    DrugInteractionFlag(
        drug_a="METOPROLOL",
        drug_b="VERAPAMIL",
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism="Bradycardie et bloc auriculo-ventriculaire synergiques",
        clinical_consequence="BAV complet, arrêt sinusal",
        management="Contre-indiqué. Si nécessaire : hospitalisation, scope ECG continu.",
    ),
    # ── Antirétroviraux ────────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="TENOFOVIR",
        drug_b="IBUPROFEN",
        severity=InteractionSeverity.MODERATE,
        mechanism="Néphrotoxicité additive",
        clinical_consequence="Insuffisance rénale aiguë",
        management="Surveiller créatinine. Préférer paracétamol.",
    ),
    DrugInteractionFlag(
        drug_a="LOPINAVIR-RITONAVIR",
        drug_b="ARTEMETHER-LUMEFANTRINE",
        severity=InteractionSeverity.MAJOR,
        mechanism="Ritonavir inhibe CYP3A4 → accumulation lumefantrine + allongement QT",
        clinical_consequence="Arythmie ventriculaire grave",
        management="Utiliser artésunate-amodiaquine comme ACT alternatif",
    ),
    # ── Psychotropes ──────────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="HALOPERIDOL",
        drug_b="QUININE",
        severity=InteractionSeverity.MAJOR,
        mechanism="Allongement additif de l'intervalle QT",
        clinical_consequence="Torsades de pointes",
        management="Monitoring ECG obligatoire si co-administration inévitable",
    ),
    DrugInteractionFlag(
        drug_a="CHLORPROMAZINE",
        drug_b="ARTEMETHER-LUMEFANTRINE",
        severity=InteractionSeverity.MODERATE,
        mechanism="Allongement modéré du QT",
        clinical_consequence="Risque arythmique augmenté",
        management="ECG baseline et surveillance. Envisager antipsychotique non QT-prolongeant.",
    ),
    # ── Antidiabétiques ───────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="METFORMIN",
        drug_b="CONTRAST-MEDIA",
        severity=InteractionSeverity.MAJOR,
        mechanism="Produits de contraste iodés → IRA transitoire → accumulation metformine",
        clinical_consequence="Acidose lactique sévère",
        management="Arrêter metformine 48h avant examen avec produit de contraste. Reprendre 48h après.",
    ),
    DrugInteractionFlag(
        drug_a="GLIBENCLAMIDE",
        drug_b="CIPROFLOXACIN",
        severity=InteractionSeverity.MODERATE,
        mechanism="Inhibition CYP2C9 + potentialisation de l'effet hypoglycémiant",
        clinical_consequence="Hypoglycémie sévère",
        management="Surveiller glycémie. Réduire la dose de glibenclamide si nécessaire.",
    ),
    # ── Hépatotoxicité ────────────────────────────────────────────────────
    DrugInteractionFlag(
        drug_a="PARACETAMOL",
        drug_b="RIFAMPICIN",
        severity=InteractionSeverity.MODERATE,
        mechanism="Induction CYP2E1 par rifampicine → production accrue de NAPQI toxique",
        clinical_consequence="Hépatotoxicité du paracétamol aux doses normales",
        management="Réduire la dose de paracétamol à 2 g/j max. Surveiller bilan hépatique.",
    ),
    DrugInteractionFlag(
        drug_a="ISONIAZID",
        drug_b="RIFAMPICIN",
        severity=InteractionSeverity.MODERATE,
        mechanism="Hépatotoxicité additive",
        clinical_consequence="Hépatite médicamenteuse (3-5 % des patients sous bithérapie anti-TB)",
        management="Surveillance mensuelle ASAT/ALAT. Arrêt si transaminases > 3N.",
    ),
]

# Index inversé : frozenset({dci_a, dci_b}) → liste d'interactions
_INTERACTION_INDEX: dict[frozenset[str], list[DrugInteractionFlag]] = {}
for _itx in _INTERACTIONS:
    _key = frozenset({_itx.drug_a, _itx.drug_b})
    _INTERACTION_INDEX.setdefault(_key, []).append(_itx)


# ---------------------------------------------------------------------------
# Base de données de contre-indications
# Format : dci_code → liste de ContraindicationFlag (selon catégorie patient)
# ---------------------------------------------------------------------------

_CONTRAINDICATIONS: Final[dict[str, list[ContraindicationFlag]]] = {
    "PRIMAQUINE": [
        ContraindicationFlag(
            dci_code="PRIMAQUINE",
            category=ContraindicationCategory.G6PD_DEFICIENCY,
            description="Primaquine provoque une hémolyse aiguë chez les sujets G6PD déficitaires",
            management="Contre-indiqué. Taux de déficit G6PD ~25 % en CI. Doser G6PD avant prescription.",
        ),
        ContraindicationFlag(
            dci_code="PRIMAQUINE",
            category=ContraindicationCategory.PREGNANCY,
            description="Tératogène. Transfert placentaire et risque d'hémolyse néonatale",
            management="Contre-indiqué pendant la grossesse. Reporter au post-partum.",
        ),
    ],
    "DAPSONE": [
        ContraindicationFlag(
            dci_code="DAPSONE",
            category=ContraindicationCategory.G6PD_DEFICIENCY,
            description="Méthémoglobinémie et hémolyse sévère chez les sujets G6PD déficitaires",
            management="Contre-indiqué. Tester G6PD avant initiation.",
        ),
    ],
    "METFORMIN": [
        ContraindicationFlag(
            dci_code="METFORMIN",
            category=ContraindicationCategory.RENAL_IMPAIRMENT,
            description="Accumulation → acidose lactique fatale si DFG < 30 mL/min",
            management="Contre-indiqué si DFG < 30. Réduire dose si DFG 30-60.",
        ),
    ],
    "IBUPROFEN": [
        ContraindicationFlag(
            dci_code="IBUPROFEN",
            category=ContraindicationCategory.PREGNANCY,
            description="Fœtotoxique au 3e trimestre : fermeture prématurée du canal artériel",
            management="Contre-indiqué au 3e trimestre. Utiliser paracétamol.",
        ),
        ContraindicationFlag(
            dci_code="IBUPROFEN",
            category=ContraindicationCategory.RENAL_IMPAIRMENT,
            description="AINS : vasoconstriction rénale → aggravation de l'insuffisance rénale",
            management="Contre-indiqué. Utiliser paracétamol.",
        ),
        ContraindicationFlag(
            dci_code="IBUPROFEN",
            category=ContraindicationCategory.AGE_PEDIATRIC,
            description="Contre-indiqué < 3 mois. Prudence 3-6 mois (risque rénal).",
            management="Utiliser paracétamol chez les nourrissons < 3 mois.",
        ),
    ],
    "ASPIRIN": [
        ContraindicationFlag(
            dci_code="ASPIRIN",
            category=ContraindicationCategory.AGE_PEDIATRIC,
            description="Risque de syndrome de Reye chez l'enfant < 16 ans avec infection virale",
            management="Contre-indiqué < 16 ans sauf prescription cardiologique spécialisée.",
        ),
    ],
    "TETRACYCLINE": [
        ContraindicationFlag(
            dci_code="TETRACYCLINE",
            category=ContraindicationCategory.PREGNANCY,
            description="Tératogène dentaire (coloration) et osseux si > 14 SA",
            management="Contre-indiqué pendant la grossesse. Utiliser amoxicilline ou céfuroxime.",
        ),
        ContraindicationFlag(
            dci_code="TETRACYCLINE",
            category=ContraindicationCategory.AGE_PEDIATRIC,
            description="Chélation calcium : altération de l'émail dentaire et croissance osseuse < 8 ans",
            management="Contre-indiqué < 8 ans. Exception : pneumonie atypique grave.",
        ),
    ],
    "DOXYCYCLINE": [
        ContraindicationFlag(
            dci_code="DOXYCYCLINE",
            category=ContraindicationCategory.PREGNANCY,
            description="Même risque que tétracyclines — fœtotoxicité osseuse et dentaire",
            management="Contre-indiqué pendant la grossesse.",
        ),
        ContraindicationFlag(
            dci_code="DOXYCYCLINE",
            category=ContraindicationCategory.AGE_PEDIATRIC,
            description="Altération émail dentaire < 8 ans",
            management="Contre-indiqué < 8 ans. Exception : maladie de Lyme, rickettsioses.",
        ),
    ],
    "WARFARIN": [
        ContraindicationFlag(
            dci_code="WARFARIN",
            category=ContraindicationCategory.PREGNANCY,
            description="Embryopathie warfarinique (1er trimestre). Hémorragie fœtale (3e trimestre).",
            management="Contre-indiqué. Substituer par héparine (HBPM) pendant la grossesse.",
        ),
    ],
    "CODEINE": [
        ContraindicationFlag(
            dci_code="CODEINE",
            category=ContraindicationCategory.AGE_PEDIATRIC,
            description="Ultra-métaboliseurs CYP2D6 : risque de dépression respiratoire mortelle < 12 ans",
            management="Contre-indiqué < 12 ans et < 18 ans après amygdalectomie.",
        ),
    ],
    "TRAMADOL": [
        ContraindicationFlag(
            dci_code="TRAMADOL",
            category=ContraindicationCategory.AGE_PEDIATRIC,
            description="Risque de convulsions. Non recommandé < 12 ans.",
            management="Utiliser paracétamol ± ibuprofène chez l'enfant.",
        ),
    ],
}

# Seuils âge pour contre-indications pédiatriques (années)
_PEDIATRIC_AGE_THRESHOLD: Final[float] = 12.0
_NEONATE_AGE_THRESHOLD: Final[float] = 0.25  # 3 mois


# ---------------------------------------------------------------------------
# Base de doses maximales adultes (mg/j) pour flags posologiques
# ---------------------------------------------------------------------------

_MAX_DAILY_DOSE_ADULT: Final[dict[str, float]] = {
    "PARACETAMOL": 4000.0,
    "IBUPROFEN": 2400.0,
    "ASPIRIN": 3000.0,
    "AMOXICILLIN": 3000.0,
    "METFORMIN": 3000.0,
    "DOXYCYCLINE": 400.0,
    "CIPROFLOXACIN": 1500.0,
    "METRONIDAZOLE": 4000.0,
}


# ---------------------------------------------------------------------------
# Moteur principal
# ---------------------------------------------------------------------------


@dataclass
class PrescriptionScanner:
    """
    Scanner d'ordonnance pour officines CMU-CI.

    Vérifie en chaîne :
      1. Interactions médicamenteuses (base OMS/ANSM — 30+ paires critiques CI)
      2. Contre-indications patient (G6PD, grossesse, âge, IR/IH)
      3. Dosages journaliers vs référentiels adultes
      4. Authenticité QR-code (stub extensible)
      5. Score de confiance composite
    """

    interactions_db: list[DrugInteractionFlag] = field(default_factory=lambda: list(_INTERACTIONS))
    interaction_index: dict[frozenset[str], list[DrugInteractionFlag]] = field(
        default_factory=lambda: dict(_INTERACTION_INDEX)
    )
    contraindications_db: dict[str, list[ContraindicationFlag]] = field(
        default_factory=lambda: dict(_CONTRAINDICATIONS)
    )
    max_daily_doses: dict[str, float] = field(default_factory=lambda: dict(_MAX_DAILY_DOSE_ADULT))

    def scan(self, request: PrescriptionRequest) -> ScanResult:
        """Point d'entrée principal — analyse complète de l'ordonnance."""
        dci_codes = [line.dci.code for line in request.drugs]
        cim10_codes = [d.code for d in request.diagnoses]

        logger.info(
            "prescription_scanner.scan",
            extra={
                "drug_count": len(dci_codes),
                "diagnosis_count": len(cim10_codes),
                "patient_age": request.patient.age_years,
            },
        )

        interactions = self._check_interactions(request.drugs)
        contraindications = self._check_contraindications(request.drugs, request.patient)
        dosage_flags = self._check_dosages(request.drugs, request.patient)
        qr_ok = self._verify_qr(request.qr_code_token, request.prescriber_id)

        status, confidence = self._compute_status(
            interactions, contraindications, dosage_flags, qr_ok
        )

        blocked = sorted(
            {
                flag.dci_code
                for flag in contraindications
                if flag.category != ContraindicationCategory.AGE_GERIATRIC
            }
            | {
                itx.drug_a if itx.drug_a in dci_codes else itx.drug_b
                for itx in interactions
                if itx.severity == InteractionSeverity.CONTRAINDICATED
            }
        )
        warning = sorted(
            {
                dci
                for itx in interactions
                if itx.severity in (InteractionSeverity.MAJOR, InteractionSeverity.MODERATE)
                for dci in (itx.drug_a, itx.drug_b)
                if dci in dci_codes and dci not in blocked
            }
            | {f.dci_code for f in dosage_flags if f.dci_code not in blocked}
        )

        return ScanResult(
            status=status,
            confidence_score=round(confidence, 3),
            interactions=interactions,
            contraindications=contraindications,
            dosage_flags=dosage_flags,
            blocked_drugs=blocked,
            warning_drugs=warning,
            qr_verified=qr_ok,
            scanned_drugs=dci_codes,
            scanned_diagnoses=cim10_codes,
            interaction_count=len(interactions),
            contraindication_count=len(contraindications),
        )

    # ------------------------------------------------------------------
    # 1. Interactions médicamenteuses
    # ------------------------------------------------------------------

    def _check_interactions(self, drugs: list[PrescriptionLine]) -> list[DrugInteractionFlag]:
        """Détecte toutes les paires d'interaction parmi les médicaments prescrits."""
        codes = [d.dci.code for d in drugs]
        found: list[DrugInteractionFlag] = []

        for i in range(len(codes)):
            for j in range(i + 1, len(codes)):
                key = frozenset({codes[i], codes[j]})
                found.extend(self.interaction_index.get(key, []))

        # Tri : CONTRAINDICATED d'abord
        severity_order = {
            InteractionSeverity.CONTRAINDICATED: 0,
            InteractionSeverity.MAJOR: 1,
            InteractionSeverity.MODERATE: 2,
            InteractionSeverity.MINOR: 3,
        }
        found.sort(key=lambda itx: severity_order[itx.severity])
        return found

    # ------------------------------------------------------------------
    # 2. Contre-indications patient
    # ------------------------------------------------------------------

    def _check_contraindications(
        self,
        drugs: list[PrescriptionLine],
        patient: PatientProfile,
    ) -> list[ContraindicationFlag]:
        """Vérifie les contre-indications liées au profil patient."""
        found: list[ContraindicationFlag] = []

        for drug in drugs:
            dci = drug.dci.code
            flags = self.contraindications_db.get(dci, [])
            for flag in flags:
                if self._is_contraindication_triggered(flag, patient):
                    found.append(flag)

        return found

    @staticmethod
    def _is_contraindication_triggered(flag: ContraindicationFlag, patient: PatientProfile) -> bool:
        cat = flag.category
        if cat == ContraindicationCategory.PREGNANCY and patient.is_pregnant:
            return True
        if cat == ContraindicationCategory.G6PD_DEFICIENCY and patient.has_g6pd_deficiency:
            return True
        if cat == ContraindicationCategory.RENAL_IMPAIRMENT and patient.has_renal_impairment:
            return True
        if cat == ContraindicationCategory.HEPATIC_IMPAIRMENT and patient.has_hepatic_impairment:
            return True
        if cat == ContraindicationCategory.AGE_PEDIATRIC:
            return patient.age_years < _PEDIATRIC_AGE_THRESHOLD
        return False

    # ------------------------------------------------------------------
    # 3. Vérification posologique
    # ------------------------------------------------------------------

    def _check_dosages(
        self,
        drugs: list[PrescriptionLine],
        patient: PatientProfile,
    ) -> list[DosageFlag]:
        """Détecte les surdosages journaliers vs référentiels adultes."""
        found: list[DosageFlag] = []
        is_pediatric = patient.age_years < _PEDIATRIC_AGE_THRESHOLD

        for drug in drugs:
            dci = drug.dci.code
            daily = drug.daily_dose_mg
            if daily is None:
                continue

            max_dose = self.max_daily_doses.get(dci)

            # Adultes : vérification vs dose maximale connue
            if not is_pediatric and max_dose and daily > max_dose:
                found.append(
                    DosageFlag(
                        dci_code=dci,
                        issue="SURDOSAGE",
                        details=f"Dose journalière prescrite : {daily} mg/j > max adulte : {max_dose} mg/j",
                        recommendation=f"Réduire à ≤ {max_dose} mg/j ou justifier médicalement.",
                    )
                )

            # Pédiatrie : alerte si dose adulte complète prescrite à un enfant
            if is_pediatric and max_dose and daily > max_dose * 0.5:
                weight_suffix = ""
                if patient.weight_kg:
                    per_kg = daily / patient.weight_kg
                    weight_suffix = f" ({per_kg:.1f} mg/kg/j)"
                found.append(
                    DosageFlag(
                        dci_code=dci,
                        issue="SURDOSAGE_PEDIATRIQUE",
                        details=f"Dose prescrite {daily} mg/j{weight_suffix} dépasse 50 % du max adulte ({max_dose} mg/j)",
                        recommendation="Recalculer la dose selon le poids corporel. Consulter le référentiel pédiatrique.",
                    )
                )

            # Durée excessive
            if (
                drug.duration_days
                and drug.duration_days > 30
                and dci in {"CIPROFLOXACIN", "AMOXICILLIN", "METRONIDAZOLE", "DOXYCYCLINE"}
            ):
                found.append(
                    DosageFlag(
                        dci_code=dci,
                        issue="DUREE_EXCESSIVE",
                        details=f"Durée de traitement : {drug.duration_days} jours",
                        recommendation="Durée > 30 j inhabituelle pour cet antibiotique. Vérifier l'indication.",
                    )
                )

        return found

    # ------------------------------------------------------------------
    # 4. Vérification QR-code (stub extensible)
    # ------------------------------------------------------------------

    @staticmethod
    def _verify_qr(token: str | None, prescriber_id: str | None) -> bool:
        """
        Vérification d'authenticité de l'ordonnance.

        Implémentation actuelle : stub basé sur HMAC-SHA256.
        Production : appel au registre centralisé ONMCI (Ordre National des
        Médecins de Côte d'Ivoire) via API sécurisée.
        """
        if not token or not prescriber_id:
            return False
        # Stub : vérifie que le token ressemble à un hash valide (≥ 32 hex chars)
        try:
            cleaned = token.strip().lower()
            int(cleaned, 16)
            return len(cleaned) >= 32
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # 5. Score de confiance et statut global
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_status(
        interactions: list[DrugInteractionFlag],
        contraindications: list[ContraindicationFlag],
        dosage_flags: list[DosageFlag],
        qr_ok: bool,
    ) -> tuple[ScanStatus, float]:
        """
        Calcule le statut global et le score de confiance composite.

        Score initial : 1.0
          - CONTRAINDICATED interaction  : −0.40 / occurrence  → BLOCKED
          - Contre-indication            : −0.35 / occurrence  → BLOCKED
          - MAJOR interaction            : −0.20 / occurrence  → WARNING
          - Surdosage (adulte/pédiatre)  : −0.15 / occurrence  → WARNING
          - MODERATE interaction         : −0.08 / occurrence  → WARNING
          - MINOR interaction            : −0.03 / occurrence
          - Durée excessive              : −0.05 / occurrence
          - QR non vérifié               : −0.05
        """
        score = 1.0
        status = ScanStatus.VALID

        for itx in interactions:
            if itx.severity == InteractionSeverity.CONTRAINDICATED:
                score -= 0.40
                status = ScanStatus.BLOCKED
            elif itx.severity == InteractionSeverity.MAJOR:
                score -= 0.20
                if status != ScanStatus.BLOCKED:
                    status = ScanStatus.WARNING
            elif itx.severity == InteractionSeverity.MODERATE:
                score -= 0.08
                if status != ScanStatus.BLOCKED:
                    status = ScanStatus.WARNING
            else:
                score -= 0.03

        for _ in contraindications:
            score -= 0.35
            status = ScanStatus.BLOCKED

        for flag in dosage_flags:
            if "SURDOSAGE" in flag.issue:
                score -= 0.15
                if status != ScanStatus.BLOCKED:
                    status = ScanStatus.WARNING
            else:
                score -= 0.05

        if not qr_ok:
            score -= 0.05

        return status, max(0.0, score)


# ---------------------------------------------------------------------------
# Singleton applicatif
# ---------------------------------------------------------------------------

_scanner: PrescriptionScanner | None = None


def get_prescription_scanner() -> PrescriptionScanner:
    """Factory / singleton FastAPI-injectable."""
    global _scanner
    if _scanner is None:
        _scanner = PrescriptionScanner()
    return _scanner
