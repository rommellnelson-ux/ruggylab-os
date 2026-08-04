"""Parseur hématologie Dymind DH36 — brouillon (manuel d'interfaçage en attente).

Tant que le protocole exact (HL7 v2 sur MLLP ou ASTM E1394) n'est pas confirmé
par la documentation constructeur, ce parseur refuse de deviner : les trames
restent archivées dans Redis (``raw_analyzer_frames``) et pourront être
rejouées ici une fois l'implémentation faite. NB :
``app.services.interfacing.dymind_dh36.DH36Parser`` contient déjà une hypothèse
HL7 branchée sur le listener MLLP historique ; à réception du manuel on
tranchera entre déléguer à ce parseur ou le remplacer ici.
"""

from __future__ import annotations

import logging

from app.services.analyzers.base import AnalyzerResultBase, BaseAnalyzerParser

logger = logging.getLogger(__name__)


class DymindHematologyParser(BaseAnalyzerParser):
    """Parseur NFS Dymind DH36 (non implémenté : protocole à confirmer)."""

    analyzer_model = "Dymind DH36"
    protocol = "unknown"

    def parse(self, raw_frame: str) -> AnalyzerResultBase:
        logger.error(
            "DymindHematologyParser.parse non implémenté : manuel d'interfaçage (HL7/ASTM) "
            "en attente. Trame de %d caractère(s) laissée dans la file Redis pour rejeu.",
            len(raw_frame),
        )
        raise NotImplementedError(
            "Parseur hématologie Dymind DH36 non implémenté : protocole (HL7 ou ASTM) à "
            "confirmer avec le manuel d'interfaçage constructeur."
        )
