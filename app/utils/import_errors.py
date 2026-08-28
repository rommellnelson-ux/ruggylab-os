"""Messages d'erreur d'import : catalogue constant, jamais dérivé d'une exception.

Les services d'import plaçaient `str(exc)` dans la liste `errors` renvoyée au
client, avec le commentaire « message de validation métier : sûr à exposer ».
C'était inexact : une ``ValidationError`` Pydantic contient le nom du modèle
interne, le chemin du champ, le type d'erreur **et la valeur d'entrée** — donc,
pour un import de patients, la donnée patient elle-même.

Une première correction reconstruisait le message depuis ``exc.errors()``. Elle
restait dérivée de l'objet exception, donc sur le chemin de flux que CodeQL
suit (`py/stack-trace-exposure`). L'approche retenue est plus stricte :

1. **valider en amont** ce qu'on sait vérifier soi-même (champ manquant,
   doublon, date illisible) et produire un **code** métier ;
2. n'utiliser ce code que pour choisir un message dans le catalogue constant
   ci-dessous ;
3. dans les blocs ``except``, **ne pas lier l'exception du tout** et émettre un
   message constant.

Ainsi aucune partie de la réponse client n'est dérivée d'un objet exception —
ni son texte, ni ses attributs, ni sa classe.
"""

from __future__ import annotations

import datetime as dt

#: Catalogue FERMÉ. La réponse client ne peut contenir que ces chaînes.
MESSAGES: dict[str, str] = {
    "champ_manquant": "Ligne rejetée — champ obligatoire manquant.",
    "identifiant_manquant": "Ligne rejetée — identifiant manquant.",
    "identifiant_duplique": "Ligne rejetée — identifiant déjà présent dans le fichier.",
    "deja_existant": "Ligne rejetée — enregistrement déjà existant.",
    "date_invalide": "Ligne rejetée — date invalide (format attendu AAAA-MM-JJ).",
    "nombre_invalide": "Ligne rejetée — valeur numérique invalide.",
    "donnees_invalides": "Ligne rejetée — données invalides.",
    "erreur_base": "Ligne rejetée (erreur base de données).",
}

#: Message servi si un code inconnu était demandé — jamais de KeyError en prod,
#: et jamais de texte imprévu dans la réponse.
_REPLI = MESSAGES["donnees_invalides"]


def message(code: str) -> str:
    """Message client pour un code métier. Toujours issu du catalogue."""
    return MESSAGES.get(code, _REPLI)


def parse_date(valeur: str | None) -> tuple[dt.date | None, str | None]:
    """(date, code d'erreur). Ne lève pas : le code remplace l'exception.

    Valider en amont évite d'avoir à rattraper une exception dont on ne pourra
    de toute façon rien exposer.
    """
    texte = (valeur or "").strip()
    if not texte:
        return None, "champ_manquant"
    try:
        return dt.date.fromisoformat(texte), None
    except ValueError:
        return None, "date_invalide"


def parse_decimal(
    valeur: str | None, *, obligatoire: bool = False
) -> tuple[str | None, str | None]:
    """(texte numérique validé, code d'erreur). Ne lève pas."""
    texte = (valeur or "").strip()
    if not texte:
        return (None, "champ_manquant") if obligatoire else (None, None)
    try:
        float(texte.replace(",", "."))
    except ValueError:
        return None, "nombre_invalide"
    return texte, None
