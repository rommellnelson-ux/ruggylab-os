"""Build FHIR R4 resources for the RuggyLab / CMU pharmacy cycle.

Resources produced:
  - DiagnosticReport   : CBC/NFS lab results        (from Result ORM objects)
  - MedicationDispense : drug dispensing to patient  (from MedicationDispenseRequest)
  - SupplyDelivery     : stock replenishment received (from SupplyDeliveryRequest)

Reference profiles:
  - DiagnosticReport:   http://hl7.org/fhir/StructureDefinition/DiagnosticReport
  - MedicationDispense: http://hl7.org/fhir/StructureDefinition/MedicationDispense
  - SupplyDelivery:     http://hl7.org/fhir/StructureDefinition/SupplyDelivery

DiagnosticReport details — maps each NFS (CBC) parameter stored in Result.data_points
to an Observation resource with LOINC codes, UCUM units, and interpretation flags.

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
from typing import Any

from app.models.ruggylab_os import Result
from app.schemas.fhir import (
    FHIRCodeableConcept,
    FHIRCoding,
    FHIRContainedPatient,
    FHIRDiagnosticReport,
    FHIRDosageInstruction,
    FHIRHumanName,
    FHIRIdentifier,
    FHIRMedicationDispense,
    FHIRMeta,
    FHIRNarrative,
    FHIRObservation,
    FHIRQuantity,
    FHIRReference,
    FHIRSupplyDelivery,
    MedicationDispenseRequest,
    SupplyDeliveryRequest,
)
from app.services.exam_catalog import exam_catalog_entry
from app.services.units import canonical_unit

# ---------------------------------------------------------------------------
# NFS parameter catalogue
# (key → LOINC code, display label, UCUM unit code, UCUM unit label)
# ---------------------------------------------------------------------------

_NFS_CATALOGUE: dict[str, tuple[str, str, str, str]] = {
    # CBC core
    "WBC": ("6690-2", "WBC [#/volume] in Blood by Automated count", "10*3/uL", "×10³/µL"),
    "RBC": ("789-8", "RBC [#/volume] in Blood by Automated count", "10*6/uL", "×10⁶/µL"),
    "HGB": ("718-7", "Hemoglobin [Mass/volume] in Blood", "g/dL", "g/dL"),
    "HCT": ("4544-3", "Hematocrit [Volume Fraction] of Blood", "%", "%"),
    "MCV": ("787-2", "MCV [Entitic volume] by Automated count", "fL", "fL"),
    "MCH": ("785-6", "MCH [Entitic mass] by Automated count", "pg", "pg"),
    "MCHC": ("786-4", "MCHC [Mass/volume] by Automated count", "g/dL", "g/dL"),
    "PLT": ("777-3", "Platelets [#/volume] in Blood by Automated count", "10*3/uL", "×10³/µL"),
    # Differential — absolute counts
    "NEUT": ("26499-4", "Neutrophils [#/volume] in Blood", "10*3/uL", "×10³/µL"),
    "LYMPH": ("26474-7", "Lymphocytes [#/volume] in Blood", "10*3/uL", "×10³/µL"),
    "MONO": ("26484-6", "Monocytes [#/volume] in Blood", "10*3/uL", "×10³/µL"),
    "EOS": ("26449-9", "Eosinophils [#/volume] in Blood", "10*3/uL", "×10³/µL"),
    "BASO": ("26444-0", "Basophils [#/volume] in Blood", "10*3/uL", "×10³/µL"),
    # Differential — percentages
    "NEUT_pct": ("770-8", "Neutrophils/100 leukocytes in Blood by Automated count", "%", "%"),
    "LYMPH_pct": ("736-9", "Lymphocytes/100 leukocytes in Blood by Automated count", "%", "%"),
    "MONO_pct": ("5905-5", "Monocytes/100 leukocytes in Blood by Automated count", "%", "%"),
    "EOS_pct": ("713-8", "Eosinophils/100 leukocytes in Blood by Automated count", "%", "%"),
    "BASO_pct": ("706-2", "Basophils/100 leukocytes in Blood by Automated count", "%", "%"),
}

_IONO_CATALOGUE: dict[str, tuple[str, str, str, str]] = {
    "NA": ("2951-2", "Sodium [Moles/volume] in Serum or Plasma", "mmol/L", "mmol/L"),
    "K": ("2823-3", "Potassium [Moles/volume] in Serum or Plasma", "mmol/L", "mmol/L"),
    "CL": ("2075-0", "Chloride [Moles/volume] in Serum or Plasma", "mmol/L", "mmol/L"),
    "CA": ("17861-6", "Calcium [Mass/volume] in Serum or Plasma", "mmol/L", "mmol/L"),
    "MG": ("19123-9", "Magnesium [Mass/volume] in Serum or Plasma", "mmol/L", "mmol/L"),
}

# RuggyLab status → FHIR interpretation code
_RUGGYLAB_STATUS_TO_FHIR: dict[str, tuple[str, str]] = {
    "NORMAL": ("N", "Normal"),
    "LOW": ("L", "Low"),
    "HIGH": ("H", "High"),
    "CRITICAL_LOW": ("LL", "Critical low"),
    "CRITICAL_HIGH": ("HH", "Critical high"),
    "N": ("N", "Normal"),
    "L": ("L", "Low"),
    "H": ("H", "High"),
    "LL": ("LL", "Critical low"),
    "HH": ("HH", "Critical high"),
    "BAS": ("L", "Low"),
    "HAUT": ("H", "High"),
    "CRITIQUE BAS": ("LL", "Critical low"),
    "CRITIQUE HAUT": ("HH", "Critical high"),
}

_INTERP_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
_LOINC_SYSTEM = "http://loinc.org"
_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0074"
_UCUM_SYSTEM = "http://unitsofmeasure.org"

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
    data_point: dict | int | float | str,
    subject_ref: str,
    effective_dt: str,
    exam_code: str | None = None,
) -> FHIRObservation | None:
    """Return a single FHIR Observation or None if the key is unknown."""
    normalized_key = param_key.upper()
    entry = _NFS_CATALOGUE.get(normalized_key) or _IONO_CATALOGUE.get(normalized_key)
    code_system = _LOINC_SYSTEM
    if entry is None:
        catalog = exam_catalog_entry(exam_code)
        if catalog and catalog.get("loinc"):
            unit = canonical_unit(data_point.get("unit")) if isinstance(data_point, dict) else None
            entry = (
                catalog["loinc"],
                catalog.get("label") or exam_code or param_key,
                unit or "",
                unit or "",
            )
        elif exam_code:
            unit = canonical_unit(data_point.get("unit")) if isinstance(data_point, dict) else None
            entry = (
                exam_code,
                (catalog or {}).get("label") or exam_code,
                unit or "",
                unit or "",
            )
            code_system = "urn:ruggylab:exam-code"
        else:
            return None

    loinc_code, display, default_ucum_code, default_ucum_label = entry
    raw_value = data_point.get("value") if isinstance(data_point, dict) else data_point
    source_unit = data_point.get("unit") if isinstance(data_point, dict) else None
    unit = canonical_unit(source_unit) or default_ucum_code
    status_value = data_point.get("status", "NORMAL") if isinstance(data_point, dict) else "NORMAL"

    obs = FHIRObservation(
        id=f"obs-{param_key.lower().replace('_', '-')}",
        status="final",
        category=[_OBS_CATEGORY],
        code=FHIRCodeableConcept(
            coding=[FHIRCoding(system=code_system, code=loinc_code, display=display)],
            text=display,
        ),
        subject=FHIRReference(reference=subject_ref),
        effectiveDateTime=effective_dt,
    )
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        quantity_unit = unit or "1"
        obs.valueQuantity = FHIRQuantity(
            value=float(raw_value),
            unit=quantity_unit or default_ucum_label,
            system=_UCUM_SYSTEM,
            code=quantity_unit,
        )
    elif raw_value is not None:
        obs.valueString = str(raw_value)
    else:
        return None
    if isinstance(data_point, dict) and data_point.get("ref_range"):
        obs.referenceRange = [{"text": str(data_point["ref_range"])}]

    # Interpretation
    status_str = str(status_value).upper()
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

    The report embeds the patient demographics and every recognised laboratory
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
        if param_key in {"overall_flags", "calibration", "manual_entry_by", "entry_timestamp"}:
            continue
        obs = _build_observation(
            param_key, data_point, patient_ref, effective_dt, result.exam_code
        )
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
    exam = exam_catalog_entry(result.exam_code) or {}
    report_label = exam.get("label") or result.exam_code or "Résultat de laboratoire"
    report_loinc = exam.get("loinc")
    category_name = exam.get("category") or "Laboratory"
    category_code = (
        "HM"
        if category_name in {"Hématologie", "Immuno-hématologie"}
        else "MB"
        if category_name in {"Microbiologie", "Parasitologie", "Sérologie"}
        else "CH"
    )
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
                f"{report_label} — RuggyLab result #{result.id}"
                f"</div>"
            ),
        ),
        contained=contained,
        identifier=[FHIRIdentifier(system="urn:ruggylab:result-id", value=str(result.id))],
        status=dr_status,
        category=[
            FHIRCodeableConcept(
                coding=[
                    FHIRCoding(
                        system=_CATEGORY_SYSTEM,
                        code=category_code,
                        display=category_name,
                    )
                ]
            )
        ],
        code=FHIRCodeableConcept(
            coding=[
                FHIRCoding(
                    system=_LOINC_SYSTEM if report_loinc else "urn:ruggylab:exam-code",
                    code=report_loinc or result.exam_code or "LAB",
                    display=report_label,
                )
            ],
            text=report_label,
        ),
        subject=FHIRReference(reference=patient_ref),
        effectiveDateTime=effective_dt,
        issued=effective_dt,
        result=obs_refs,
        conclusionCode=conclusion_codes,
    )

    return report


# ---------------------------------------------------------------------------
# Systèmes de terminologie partagés
# ---------------------------------------------------------------------------

_ATC_SYSTEM = "http://www.whocc.no/atc"
_SNOMED_SYSTEM = "http://snomed.info/sct"
_SUPPLY_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/supply-kind"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_iso(value: str | None) -> str:
    """Return value if provided, otherwise today in ISO-8601."""
    return value or datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# MedicationDispense bundle
# ---------------------------------------------------------------------------


def build_medication_dispense_bundle(
    request: MedicationDispenseRequest,
) -> dict[str, Any]:
    """
    Construit un Bundle FHIR R4 de type ``collection`` contenant un
    ``MedicationDispense`` par ligne de médicament dispensé.

    Chaque ressource est liée au patient, au prescripteur (si fourni) et
    à la prescription autorisant la dispensation (si fournie).

    Args:
        request: données de dispensation validées (Pydantic).

    Returns:
        dict sérialisable en JSON conforme FHIR R4 Bundle.
    """
    dispensed_at = request.dispensed_at or _now_iso()
    entries: list[dict[str, Any]] = []

    subject_ref = FHIRReference(reference=f"urn:ruggylab:patient:{request.patient_ref}")
    auth_prescriptions: list[FHIRReference] = []
    if request.authorizing_prescription_ref:
        auth_prescriptions = [FHIRReference(reference=request.authorizing_prescription_ref)]

    performer: list[dict] = []
    if request.practitioner_ref:
        performer = [
            {"actor": {"reference": f"urn:ruggylab:practitioner:{request.practitioner_ref}"}}
        ]

    for idx, line in enumerate(request.drug_lines, start=1):
        resource_id = f"disp-{idx:04d}"

        # Posologie
        dosage: list[FHIRDosageInstruction] = []
        if line.dose_mg is not None or line.route:
            parts: list[str] = []
            if line.dose_mg:
                parts.append(f"{line.dose_mg} mg")
            if line.frequency_per_day:
                parts.append(f"{line.frequency_per_day}×/j")
            if line.duration_days:
                parts.append(f"pendant {line.duration_days} j")
            dosage_text = " — ".join(parts) if parts else line.route

            route_concept = FHIRCodeableConcept(
                coding=[
                    FHIRCoding(
                        system=_SNOMED_SYSTEM,
                        code="26643006" if line.route == "oral" else "47625008",
                        display="Oral route" if line.route == "oral" else line.route,
                    )
                ],
                text=line.route,
            )
            dose_rate: list[dict] = []
            if line.dose_mg is not None:
                dose_rate = [
                    {
                        "doseQuantity": {
                            "value": line.dose_mg,
                            "unit": "mg",
                            "system": _UCUM_SYSTEM,
                            "code": "mg",
                        }
                    }
                ]
            dosage = [
                FHIRDosageInstruction(
                    text=dosage_text,
                    route=route_concept,
                    doseAndRate=dose_rate,
                )
            ]

        # Quantité dispensée
        quantity = FHIRQuantity(
            value=float(line.quantity),
            unit="unité",
            system=_UCUM_SYSTEM,
            code="1",
        )

        # Note CMU
        notes: list[dict[str, str]] = []
        if request.cnam_billing_ref:
            notes.append({"text": f"Dossier CMU CNAM : {request.cnam_billing_ref}"})

        dispense = FHIRMedicationDispense(
            id=resource_id,
            meta=FHIRMeta(
                profile=["http://hl7.org/fhir/StructureDefinition/MedicationDispense"],
                lastUpdated=dispensed_at,
            ),
            status="completed",
            medicationCodeableConcept=FHIRCodeableConcept(
                coding=[
                    FHIRCoding(
                        system=_ATC_SYSTEM,
                        code=line.dci_code,
                        display=line.dci_code,
                    )
                ],
                text=line.dci_code,
            ),
            subject=subject_ref,
            performer=performer,
            authorizingPrescription=auth_prescriptions,
            quantity=quantity,
            whenHandedOver=dispensed_at,
            dosageInstruction=dosage,
            note=notes,
        )

        entries.append(
            {
                "fullUrl": f"urn:uuid:{resource_id}",
                "resource": dispense.model_dump(exclude_none=True),
            }
        )

    bundle_meta: dict[str, Any] = {}
    if request.pharmacy_id:
        bundle_meta["pharmacy_id"] = request.pharmacy_id

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": dispensed_at,
        "total": len(entries),
        "entry": entries,
        # Extension locale CMU (hors namespace FHIR standard)
        "_cmu_context": bundle_meta or None,
    }


# ---------------------------------------------------------------------------
# SupplyDelivery bundle
# ---------------------------------------------------------------------------

# Type de livraison : réassort pharmaceutique
_SUPPLY_DELIVERY_TYPE = FHIRCodeableConcept(
    coding=[
        FHIRCoding(
            system=_SUPPLY_TYPE_SYSTEM,
            code="medication",
            display="Medication",
        )
    ],
    text="Réassort médicament",
)


def build_supply_delivery_bundle(
    request: SupplyDeliveryRequest,
) -> dict[str, Any]:
    """
    Construit un Bundle FHIR R4 de type ``collection`` contenant un
    ``SupplyDelivery`` par article livré.

    Chaque ressource trace :
      - l'article livré (DCI OMS + quantité)
      - le fournisseur (grossiste ou NPSP)
      - l'officine destinataire
      - la date de livraison
      - la référence MedicationRequest si la commande est tracée

    Args:
        request: données de livraison validées (Pydantic).

    Returns:
        dict sérialisable en JSON conforme FHIR R4 Bundle.
    """
    delivery_date = _date_iso(request.delivery_date)
    entries: list[dict[str, Any]] = []

    supplier_ref = FHIRReference(
        reference=f"urn:ruggylab:organization:{request.supplier_name.replace(' ', '-')}",
        display=request.supplier_name,
    )
    destination_ref = FHIRReference(
        reference=f"urn:ruggylab:location:{request.destination_pharmacy_id}",
        display=request.destination_pharmacy_id,
    )
    based_on: list[FHIRReference] = []
    if request.order_reference:
        based_on = [FHIRReference(reference=request.order_reference)]

    for idx, item in enumerate(request.items, start=1):
        resource_id = f"supply-del-{idx:04d}"

        # Article livré
        supplied_item: dict[str, Any] = {
            "quantity": {
                "value": float(item.quantity),
                "unit": "unité",
                "system": _UCUM_SYSTEM,
                "code": "1",
            },
            "itemCodeableConcept": {
                "coding": [
                    {
                        "system": _ATC_SYSTEM,
                        "code": item.dci_code,
                        "display": item.dci_code,
                    }
                ],
                "text": item.dci_code,
            },
        }

        # Notes : lot + péremption + valorisation
        notes: list[dict[str, str]] = []
        if item.batch_number:
            notes.append({"text": f"Lot : {item.batch_number}"})
        if item.expiry_date:
            notes.append({"text": f"Date péremption : {item.expiry_date}"})
        if item.unit_cost_xof is not None:
            total_xof = item.unit_cost_xof * item.quantity
            notes.append(
                {
                    "text": (
                        f"Valorisation : {item.unit_cost_xof} XOF/unité × "
                        f"{item.quantity} = {total_xof:.0f} XOF"
                    )
                }
            )

        delivery = FHIRSupplyDelivery(
            id=resource_id,
            meta=FHIRMeta(
                profile=["http://hl7.org/fhir/StructureDefinition/SupplyDelivery"],
                lastUpdated=delivery_date,
            ),
            status="completed",
            type=_SUPPLY_DELIVERY_TYPE,
            suppliedItem=supplied_item,
            occurrenceDateTime=delivery_date,
            supplier=supplier_ref,
            destination=destination_ref,
            basedOn=based_on,
            note=notes,
        )

        entries.append(
            {
                "fullUrl": f"urn:uuid:{resource_id}",
                "resource": delivery.model_dump(exclude_none=True),
            }
        )

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": delivery_date,
        "total": len(entries),
        "entry": entries,
    }
