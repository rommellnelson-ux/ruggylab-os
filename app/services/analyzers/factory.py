"""Factory de parseurs d'automates : ``AnalyzerKind`` -> ``BaseAnalyzerParser``.

Point d'entrée unique du dépilage futur : le worker qui videra
``raw_analyzer_frames`` lira le champ ``analyzer_kind`` de chaque trame et
demandera ici l'instance de parseur adaptée. Ajouter un automate = enregistrer
une entrée dans ``_REGISTRY`` (aucun ``if/elif`` disséminé).
"""

from __future__ import annotations

from app.services.analyzers.anbio_immuno import AnbioImmunoParser
from app.services.analyzers.base import BaseAnalyzerParser
from app.services.analyzers.dymind_biochemistry import DymindBiochemistryParser
from app.services.analyzers.dymind_hematology import DymindHematologyParser
from app.services.analyzers.registry import AnalyzerKind

# Registre déclaratif kind -> classe de parseur.
_REGISTRY: dict[AnalyzerKind, type[BaseAnalyzerParser]] = {
    AnalyzerKind.HEMATOLOGY: DymindHematologyParser,
    AnalyzerKind.BIOCHEMISTRY: DymindBiochemistryParser,
    AnalyzerKind.IMMUNO: AnbioImmunoParser,
}


class AnalyzerParserFactory:
    """Fabrique le parseur correspondant à un ``AnalyzerKind``."""

    @staticmethod
    def get_parser(kind: AnalyzerKind | str) -> BaseAnalyzerParser:
        """Retourne une instance de parseur pour ce discriminateur.

        ``kind`` accepte l'enum ou sa valeur brute (telle que lue dans le JSON
        Redis). Lève ``KeyError`` si le kind est inconnu.
        """
        if isinstance(kind, str):
            kind = AnalyzerKind(kind)
        parser_cls = _REGISTRY.get(kind)
        if parser_cls is None:  # pragma: no cover - garde-fou défensif
            raise KeyError(f"Aucun parseur enregistré pour l'automate {kind!r}")
        return parser_cls()

    @staticmethod
    def supported_kinds() -> list[AnalyzerKind]:
        return list(_REGISTRY)
