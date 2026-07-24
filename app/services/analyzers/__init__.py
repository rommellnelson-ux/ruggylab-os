"""Parseurs d'automates (abstractions, factory + implémentations par modèle).

Sépare la *réception* des trames (app.services.interfacing.raw_tcp_listener,
qui capture en aveugle vers Redis) de leur *interprétation* (les parseurs de ce
paquet, qui transforment une trame brute en ``AnalyzerResultBase`` normalisé).
Le routage réception -> parseur passe par ``AnalyzerKind`` (registry) et
``AnalyzerParserFactory`` (factory).
"""

from app.services.analyzers.anbio_immuno import AnbioImmunoParser
from app.services.analyzers.base import AnalyzerResultBase, BaseAnalyzerParser
from app.services.analyzers.dymind_biochemistry import DymindBiochemistryParser
from app.services.analyzers.dymind_hematology import DymindHematologyParser
from app.services.analyzers.factory import AnalyzerParserFactory
from app.services.analyzers.registry import (
    AnalyzerBinding,
    AnalyzerKind,
    default_bindings,
    enabled_bindings,
)

# Alias de rétrocompat : l'ancien nom du stub hématologie.
DymindDH36Parser = DymindHematologyParser

__all__ = [
    "AnalyzerBinding",
    "AnalyzerKind",
    "AnalyzerParserFactory",
    "AnalyzerResultBase",
    "AnbioImmunoParser",
    "BaseAnalyzerParser",
    "DymindBiochemistryParser",
    "DymindDH36Parser",
    "DymindHematologyParser",
    "default_bindings",
    "enabled_bindings",
]
