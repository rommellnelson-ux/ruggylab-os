"""Build FHIR R4 DiagnosticReport documents from RuggyLab Result objects.

Maps each NFS (CBC) parameter stored in Result.data_points to an
Observation resource with:
  - LOINC code (system http://loinc.org)
  - UCUM unit  (system http://unitsofmeasure.org)
  - Interpretation flag derived from RuggyLab's own status value
    ("LOW", "HIGH", "CRITICAL_LOW", "CRITICAL_HIGH", "NORMAL")

The produced document is self-contained (all Observations and the Patient
are embedded as `contained` resources) so it can be handed to any FHIR
server without prior resource registration.

Reference profiles used:
  - DiagnosticReport: http://hl7.org/fhir/StructureDefinition/DiagnosticReport
  - Observation:      http://hl7.org/fhir/StructureDefinition/Observation
"""

from __future__ import annotations

import datetime

from app.models.ruggylab_os import Result
from app.schemas.fhir import (
    FHIRCodeableConcept,
    FHIRCoding,
    FHIRContainedPatient,
    FHIRDiagnosticReport,
    FHIRHumanName,
    FHIRIdentifier,
    FHIRMeta,
    FHIRNarrative,
    FHIRObservation,
    FHIRQuantity,
    FHIRReference,
)

# ---------------------------------------------------------------------------
# NFS parameter catalogue
# (key → LOINC code, display label, UCUM unit code, UCUM unit label)
# ---------------------------------------------------------------------------

_NFS_CATALOGUE: dict[str, tuple[str, str, str, str]] = {
    # CBC core
    "WBC":  ("6690-2",  "WBC [#/volume] in Blood by Automated count",   "10*3/uL", "×10³/µL"),
    "RBC":  ("789-8",   "RBC [#/volume] in Blood by Automated count",   "10*6/uL", "×10⁶/µL"),
    "HGB":  ("718-7",   "Hemoglobin [Mass/volume] in Blood",             "g/dL",    "g/dL"),
    "HCT":  ("4544-3",  "Hematocrit [Volume Fraction] of Blood",         "%",       "%"),
    "MCV":  ("787-2",   "MCV [Entitic volume] by Automated count",       "fL",      "fL"),
    "MCH":  ("785-6",   "MCH [Entitic mass] by Automated count",         "pg",      "pg"),
    "MCHC": ("786-4",   "MCHC [Mass/volume] by Automated count",         "g/dL",    "g/dL"),
    "PLT":  ("777-3",   "Platelets [#/volume] in Blood by Automated count","10*3/uL","×10³/µL"),
    # Differential — absolute counts
    "NEUT": ("26499-4", "Neutrophils [#/volume] in Blood",               "10*3/uL", "×10³/µL"),
    "LYMPH":("26474-7", "Lymphocytes [#/volume] in Blood",               "10*3/uL", "×10³/µL"),
    "MONO": ("26484-6", "Monocytes [#/volume] in Blood",                 "10*3/uL", "×10³/µL"),
    "EOS":  ("26449-9", "Eosinophils [#/volume] in Blood",               "10*3/uL", "×10³/µL"),
    "BASO": ("26444-0", "Basophils [#/volume] in Blood",                 "10*3/uL", "×10³/µL"),
    # Differential — percentages
    "NEUT_pct": ("770-8",   "Neutrophils/100 leukocytes in Blood by Automated count", "%", "%"),
    "LYMPH_pct":("736-9",   "Lymphocytes/100 leukocytes in Blood by Automated count","%", "%"),
    "MONO_pct": ("5905-5",  "Monocytes/100 leukocytes in Blood by Automated count",  "%", "%"),
    "EOS_pct":  ("713-8",   "Eosinophils/100 leukocytes in Blood by Automated count","%", "%"),
    "BASO_pct": ("706-2",   "Basophils/100 leukocytes in Blood by Automated count",  "%", "%"),
}

# RuggyLab status → FHIR interpretation code
_RUGGYLAB_STATUS_TO_FHIR: dict[str, tuple[str, str]] = {
    "NORMAL":        ("N",  "Normal"),
    "LOW":           ("L",  "Low"),
    "HIGH":          ("H",  "High"),
    "CRITICAL_LOW":  ("LL", "Critical low"),
    "CRITICAL_HIGH": ("HH", "Critical high"),
}

_INTERP_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
_LOINC_SYSTEM  = "http://loinc.org"
_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0074"
_UCUM_SYSTEM   = "http://unitsofmeasure.org"

_OBS_CATEGORY = FHIRCodeableConcept(
    coding=[
        FHIRCoding(
            system="http://terminology.hl7.org/CodeSystem/observation-category",
            code="laboratory",
            display="Laboratory",
        )
    ]
)


def _build_observation(
    param_key: str,
    data_point: dict,
    subject_ref: str,
    effective_dt: str,
) -> FHIRObservation | None:
    """Return a single FHIR Observation or None if the key is unknown."""
    entry = _NFS_CATALOGUE.get(param_key)
    if entry is None:
        return None

    loinc_code, display, ucum_code, ucum_label = entry
    raw_value = data_point.get("value")
    if raw_value is None:
        return None

    obs = FHIRObservation(
        id=f"obs-{param_key.lower().replace('_', '-')}",
        status="final",
        category=[_OBS_CATEGORY],
        code=FHIRCodeableConcept(
            coding=[FHIRCoding(system=_LOINC_SYSTEM, code=loinc_code, display=display)],
            text=display,
        ),
        subject=FHIRReference(reference=subject_ref),
        effectiveDateTime=effective_dt,
        valueQuantity=FHIRQuantity(
            value=float(raw_value),
            unit=ucum_label,
            system=_UCUM_SYSTEM,
            code=ucum_code,
        ),
    )

    # Interpretation
    status_str = str(data_point.get("status", "NORMAL")).upper()
    fhir_interp = _RUGGYLAB_STATUS_TO_FHIR.get(status_str)
    if fhir_interp:
        obs.interpretation = [
            FHIRCodeableConcept(
                coding=[
                    FHIRCoding(
                        system=_INTERP_SYSTEM,
                        code=fhir_interp[0],
                        display=fhir_interp[1],
                    )
                ]
            )
        ]

    return obs


def build_diagnostic_report(result: Result) -> FHIRDiagnosticReport:
    """Convert a RuggyLab ``Result`` ORM object to a FHIR R4 DiagnosticReport.

    The report embeds the patient demographics and every recognised CBC
    parameter as contained Observation resources.

    Args:
        result: SQLAlchemy ``Result`` instance (with relationships loaded).

    Returns:
        A fully-populated ``FHIRDiagnosticReport`` ready to be serialised
        as JSON.
    """
    report_id = f"ruggylab-result-{result.id}"

    # ---- Effective date ------------------------------------------------
    if result.analysis_date:
        effective_dt = result.analysis_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        effective_dt = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- Patient contained resource ------------------------------------
    contained: list = []
    patient_ref = "#patient-unknown"

    sample = result.sample
    patient = sample.patient if sample else None

    if patient:
        patient_id = f"patient-{patient.id}"
        patient_ref = f"#{patient_id}"
        gender_map = {"M": "male", "F": "female", "m": "male", "f": "female"}
        contained_patient = FHIRContainedPatient(
            id=patient_id,
            identifier=[
                FHIRIdentifier(
                    system="urn:ruggylab:ipp",
                    value=patient.ipp_unique_id,
                )
            ],
            name=[
                FHIRHumanName(
                    family=patient.last_name,
                    given=[patient.first_name],
                )
            ],
            birthDate=patient.birth_date.isoformat() if patient.birth_date else None,
            gender=gender_map.get(patient.sex or ""),
        )
        contained.append(contained_patient)

    # ---- Observations --------------------------------------------------
    data_points: dict = result.data_points or {}
    obs_refs: list[FHIRReference] = []

    for param_key, data_point in data_points.items():
        if not isinstance(data_point, dict):
            # Some keys (e.g. "overall_flags", "malaria_ai") are not numeric
            continue
        obs = _build_observation(param_key, data_point, patient_ref, effective_dt)
        if obs:
            contained.append(obs)
            obs_refs.append(FHIRReference(reference=f"#{obs.id}"))

    # ---- Overall flags as conclusionCode -------------------------------
    conclusion_codes: list[FHIRCodeableConcept] = []
    overall_flags = data_points.get("overall_flags", [])
    if isinstance(overall_flags, list):
        for flag in overall_flags:
            conclusion_codes.append(
                FHIRCodeableConcept(
                    coding=[
                        FHIRCoding(
                            system="urn:ruggylab:clinical-flag",
                            code=flag,
                            display=flag,
                        )
                    ],
                    text=flag,
                )
            )

    # ---- DiagnosticReport status ---------------------------------------
    dr_status = "final" if result.is_validated else "preliminary"

    # ---- Assemble the report -------------------------------------------
    report = FHIRDiagnosticReport(
        id=report_id,
        meta=FHIRMeta(
            profile=["http://hl7.org/fhir/StructureDefinition/DiagnosticReport"],
            lastUpdated=effective_dt,
        ),
        text=FHIRNarrative(
            status="generated",
            div=(
                f"<div xmlns='http://www.w3.org/1999/xhtml'>"
                f"CBC DiagnosticReport — RuggyLab result #{result.id}"
                f"</div>"
            ),
        ),
        contained=contained,
        identifier=[
            FHIRIdentifier(system="urn:ruggylab:result-id", value=str(result.id))
        ],
        status=dr_status,
        category=[
            FHIRCodeableConcept(
                coding=[
                    FHIRCoding(
                        system=_CATEGORY_SYSTEM,
                        code="HM",
                        display="Hematology",
                    )
                ]
            )
        ],
        code=FHIRCodeableConcept(
            coding=[
                FHIRCoding(
                    system=_LOINC_SYSTEM,
                    code="58410-2",
                    display="CBC panel - Blood by Automated count",
                )
            ],
            text="Numération Formule Sanguine (NFS/CBC)",
        ),
        subject=FHIRReference(reference=patient_ref),
        effectiveDateTime=effective_dt,
        issued=effective_dt,
        result=obs_refs,
        conclusionCode=conclusion_codes,
    )

    return report
