"""Neutralisation de l'injection de formules CSV (CSV/formula injection).

Une cellule commençant par =, +, -, @ (ou une tabulation / retour chariot)
peut être interprétée comme une formule par Excel / LibreOffice / Google Sheets.
On la préfixe d'une apostrophe pour forcer un traitement en texte.
"""

from __future__ import annotations

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: object) -> object:
    """Préfixe la valeur d'une apostrophe si elle peut déclencher une formule.

    Les valeurs non textuelles (int, float, bool, None) sont renvoyées telles
    quelles — seules les chaînes sont concernées.
    """
    if not isinstance(value, str):
        return value
    if value and value[0] in _DANGEROUS_PREFIXES:
        return "'" + value
    return value
