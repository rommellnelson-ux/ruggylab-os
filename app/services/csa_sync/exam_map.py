"""Correspondance des référentiels d'examens CSA Plateau → RuggyLab OS.

CSA code ses examens dans une nomenclature type NGAP (``BEDA005``, ``BNDA008``…) ;
RuggyLab utilise des codes cliniques courts (``NFS``, ``GLYC``…, cf.
``app/services/exam_catalog.py``). Cette table est **curée à la main** — jamais
devinée. Un code CSA sans correspondance produit un item ``unmapped`` signalé,
JAMAIS silencieusement perdu.

Un code CSA peut se mapper vers **plusieurs** codes RuggyLab (bilans groupés :
« bilan rénal » → UREE + CREAT ; « bilan lipidique » → CHOL + TG + HDL + LDL).

Les actes de soins CSA (préfixe ``T`` : injections, pansements, sutures…) ne sont
pas des examens de laboratoire et restent volontairement non mappés.
"""

from __future__ import annotations

# CSA LABO_ACTES  ->  liste de codes EXAM_CATALOG RuggyLab.
CSA_TO_RUGGYLAB: dict[str, list[str]] = {
    # ── Hématologie ──
    "BEDA005": ["NFS"],  # NFS / Hémogramme complet
    "BEDC001": ["GRH"],  # Groupage ABO-Rh(D)
    "BEDD001": ["VS"],  # Vitesse de sédimentation
    # ── Biochimie ──
    "BNDA008": ["GLYC"],  # Glycémie
    "BNDA009": ["HBA1C"],  # HbA1c
    "BNDA012": ["UREE"],  # Urée
    "BNDA013": ["CREAT"],  # Créatinine
    "BNDA014": ["UREE", "CREAT"],  # Bilan rénal (urée + créatinine)
    "BLDA007": ["ALAT", "ASAT"],  # Transaminases
    "BLDA005": ["ALAT"],
    "BLDA006": ["ASAT"],
    "BMDA003": ["CRP"],  # CRP
    "BNDC001": ["CALC"],  # Calcium
    "BNDB002": ["URIC"],  # Acide urique
    "BNDB001": ["CHOL"],  # Cholestérol total
    "BNDB003": ["TG"],  # Triglycérides
    "BNDB005": ["CHOL", "TG", "HDL", "LDL"],  # Bilan lipidique complet
    # ── Immuno / sérologie / parasito ──
    "BYDZ004": ["AGHBS"],  # TDR AgHBs
    "BGDE071": ["HIV"],  # TDR VIH 1&2
    "BGDC019": ["WIDAL"],  # Widal
    "BYDZ001": ["GE"],  # TDR Paludisme -> goutte épaisse (paludisme)
    "BFDB006": ["GE"],  # Goutte épaisse / frottis
    "BFDB007": ["GE"],  # GE + frottis + TDR
    # ── Bactériologie ──
    "BFDA001": ["ECBU"],  # ECBU
}


def map_exam(csa_code: str | None) -> list[str]:
    """Renvoie les codes RuggyLab correspondant à un code d'examen CSA.

    Liste vide = aucun mapping connu (l'appelant marquera l'item ``unmapped``).
    """
    if not csa_code:
        return []
    return list(CSA_TO_RUGGYLAB.get(csa_code.strip().upper(), []))


def is_mapped(csa_code: str | None) -> bool:
    return bool(map_exam(csa_code))
