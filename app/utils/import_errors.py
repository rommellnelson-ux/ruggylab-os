"""Messages d'erreur d'import : construits, jamais recopiés depuis l'exception.

Les services d'import en masse plaçaient `str(exc)` dans la liste `errors`
renvoyée au client, avec le commentaire « message de validation métier : sûr à
exposer ». Ce n'est pas exact :

- une ``ValidationError`` Pydantic contient le nom du modèle interne, le chemin
  du champ, le type d'erreur **et la valeur d'entrée** — donc, pour un import de
  patients, la donnée patient elle-même, renvoyée telle quelle dans la réponse ;
- une ``ValueError`` peut venir de n'importe quelle bibliothèque appelée en
  chemin, et son texte n'est alors contrôlé par personne.

Ce module transforme l'exception en message **construit à partir de champs
connus**. Le lien entre l'erreur et sa cause est conservé — c'est ce dont
l'opérateur a besoin pour corriger son fichier — sans recopier de texte
d'exception dans la réponse HTTP.
"""

from __future__ import annotations

from pydantic import ValidationError

#: Traductions des types d'erreur Pydantic les plus courants sur un import CSV.
#: Vocabulaire fermé : rien de ce qui sort d'ici ne vient de l'exception.
_RAISONS = {
    "missing": "valeur manquante",
    "string_too_long": "valeur trop longue",
    "string_too_short": "valeur trop courte",
    "string_pattern_mismatch": "format invalide",
    "date_parsing": "date invalide",
    "date_from_datetime_parsing": "date invalide",
    "date_type": "date invalide",
    "int_parsing": "nombre entier attendu",
    "int_type": "nombre entier attendu",
    "float_parsing": "nombre attendu",
    "decimal_parsing": "nombre attendu",
    "greater_than": "valeur trop petite",
    "greater_than_equal": "valeur trop petite",
    "less_than": "valeur trop grande",
    "less_than_equal": "valeur trop grande",
    "enum": "valeur hors des choix autorisés",
    "literal_error": "valeur hors des choix autorisés",
    "value_error": "valeur invalide",
    "bool_parsing": "oui/non attendu",
}

_RAISON_PAR_DEFAUT = "valeur invalide"
_MESSAGE_GENERIQUE = "Ligne rejetée (données invalides)."


def _champ(localisation: tuple[object, ...]) -> str:
    """Nom du champ fautif, ou chaîne vide si Pydantic n'en désigne aucun."""
    parties = [str(p) for p in localisation if isinstance(p, str)]
    return ".".join(parties)


def describe_validation_error(exc: Exception) -> str:
    """Message sûr décrivant une erreur de validation de ligne.

    Ne renvoie que des libellés issus d'un vocabulaire fermé et des noms de
    champs du schéma. La valeur saisie et le texte de l'exception n'y figurent
    jamais.
    """
    if isinstance(exc, ValidationError):
        details = exc.errors()
        if not details:
            return _MESSAGE_GENERIQUE
        problemes: list[str] = []
        for detail in details[:5]:  # au-delà, la ligne est à refaire de toute façon
            raison = _RAISONS.get(str(detail.get("type", "")), _RAISON_PAR_DEFAUT)
            nom = _champ(tuple(detail.get("loc", ())))
            problemes.append(f"{nom} : {raison}" if nom else raison)
        reste = len(details) - len(problemes)
        suffixe = f" (+{reste} autre(s))" if reste > 0 else ""
        return f"Ligne rejetée — {'; '.join(problemes)}{suffixe}."

    # `ValueError` non-Pydantic : le texte vient d'une bibliothèque quelconque
    # en chemin, personne ne le contrôle. On ne le propage donc pas.
    return _MESSAGE_GENERIQUE
