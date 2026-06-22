"""Compte-rendu d'examens consolidé : un PDF regroupant tous les résultats
d'une prescription (le « fil »), remis au patient/médecin.

Texte sans accents : le générateur PDF minimal encode en latin-1.
"""

from __future__ import annotations

from app.models import ExamOrder, Result
from app.services.pdf import build_simple_pdf

_PRIORITY = {"routine": "Routine", "urgent": "Urgent", "stat": "STAT (immediat)"}


def build_order_report_pdf(order: ExamOrder, results: dict[int, Result]) -> bytes:
    """Construit le compte-rendu consolidé d'une prescription.

    ``results`` : map result_id -> Result pour les examens déjà résultés.
    """
    patient = order.patient
    name = f"{patient.first_name} {patient.last_name}" if patient else "N/A"
    lines: list[str] = [
        "RuggyLab OS - Compte-rendu d'examens",
        "",
        f"Prescription : #{order.id}",
        f"Patient      : {name}",
        f"IPP          : {patient.ipp_unique_id if patient else 'N/A'}",
        f"Sexe         : {patient.sex if patient and patient.sex else '-'}",
        f"Prescripteur : {order.prescriber or '-'}",
        f"Date         : {order.ordered_at:%d/%m/%Y %H:%M}",
        f"Priorite     : {_PRIORITY.get(order.priority, order.priority)}",
        "-" * 56,
    ]

    resulted = 0
    for item in order.items:
        if item.status == "cancelled":
            continue
        lines.append("")
        title = f"[{item.exam_code}] {item.exam_label or ''}".strip()
        lines.append(title)
        res = results.get(item.result_id) if item.result_id else None
        if res is None:
            lines.append("  En attente de resultat")
            continue
        resulted += 1
        flags = res.flags or {}
        for key, value in sorted((res.data_points or {}).items()):
            if isinstance(value, dict):
                disp = value.get("value", value)
                unit = value.get("unit", "")
                stat = value.get("status", "")
                lines.append(f"  - {key}: {disp} {unit} {stat}".rstrip())
            else:
                fl = flags.get(key, "")
                suffix = f" [{fl}]" if fl else ""
                lines.append(f"  - {key}: {value}{suffix}")
        if res.bioref_status:
            lines.append(f"  Interpretation: {res.bioref_status}")
        lines.append(
            f"  Valide: {'oui' if res.is_validated else 'non'}"
            f" - Critique: {'oui' if res.is_critical else 'non'}"
        )

    lines += [
        "",
        "-" * 56,
        f"Examens resultes : {resulted}/{sum(1 for i in order.items if i.status != 'cancelled')}",
        "Compte-rendu genere par RuggyLab OS.",
    ]
    return build_simple_pdf(lines)
