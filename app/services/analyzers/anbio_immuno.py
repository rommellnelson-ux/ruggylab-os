"""Parseur immunofluorescence Anbio Bioscann — brouillon (manuel en attente)."""

from __future__ import annotations

import logging

from app.services.analyzers.base import AnalyzerResultBase, BaseAnalyzerParser

logger = logging.getLogger(__name__)


class AnbioImmunoParser(BaseAnalyzerParser):
    """Parseur immuno Anbio Bioscann (non implémenté : protocole à confirmer)."""

    analyzer_model = "Anbio Bioscann"
    protocol = "unknown"

    def parse(self, raw_frame: str) -> AnalyzerResultBase:
        logger.error(
            "AnbioImmunoParser.parse non implémenté : manuel d'interfaçage en attente. "
            "Trame de %d caractère(s) laissée dans la file Redis pour rejeu.",
            len(raw_frame),
        )
        raise NotImplementedError(
            "Parseur immuno Anbio Bioscann non implémenté : protocole à confirmer avec le "
            "manuel d'interfaçage constructeur."
        )
