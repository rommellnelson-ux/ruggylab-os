"""Génération du reçu PDF d'une facture (FCFA), via le générateur PDF minimal.

Texte volontairement sans accents : le générateur encode en latin-1 et le rendu
reste ainsi propre quel que soit l'environnement.
"""

from __future__ import annotations

from decimal import Decimal

from app.models import Invoice
from app.services.accounting_service import balance_of
from app.services.pdf import build_simple_pdf

_PATIENT_TYPE_LABELS = {"INSURED": "Assure CNAM", "UNINSURED": "Non assure"}


def _xof(value: Decimal | int | float | None) -> str:
    """Formate un montant en FCFA entier avec separateur de milliers (espace)."""
    return f"{int(Decimal(value or 0)):,}".replace(",", " ") + " FCFA"


def build_invoice_receipt_pdf(invoice: Invoice) -> bytes:
    lines: list[str] = [
        "RuggyLab OS - Recu / Facture",
        "",
        f"Facture   : {invoice.invoice_number}",
        f"Date      : {invoice.issued_at:%d/%m/%Y %H:%M}",
        f"Patient   : {invoice.patient_label or '-'}",
        f"Couverture: {_PATIENT_TYPE_LABELS.get(invoice.patient_type, invoice.patient_type)}"
        + (f" ({invoice.insurance_id})" if invoice.insurance_id else ""),
        "-" * 56,
        "Examens factures :",
    ]
    for line in invoice.lines:
        lines.append(
            f"  {line.label} x{line.quantity}"
            f"  {_xof(line.unit_price_xof)}  =  {_xof(line.line_total_xof)}"
        )
    lines += [
        "-" * 56,
        f"Total brut            : {_xof(invoice.gross_total_xof)}",
        f"Remise                : {_xof(invoice.discount_xof)}",
        f"Net                   : {_xof(invoice.net_total_xof)}",
        f"Part CNAM (70%)       : {_xof(invoice.cnam_part_xof)}",
        f"Reste a charge patient: {_xof(invoice.patient_due_xof)}",
        f"Encaisse              : {_xof(invoice.paid_xof)}",
        f"Solde du              : {_xof(balance_of(invoice))}",
        "-" * 56,
        f"Statut    : {invoice.status}",
        "",
        "Facturation conforme CMU Cote d'Ivoire (CNAM 70% / ticket 30%).",
    ]
    return build_simple_pdf(lines)
