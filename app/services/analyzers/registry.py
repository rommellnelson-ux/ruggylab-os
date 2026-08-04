"""Registre des automates TCP : discriminateur ``AnalyzerKind`` + bindings réseau.

Le routage est **par port** (un listener par automate) : déterministe et
aligné sur la segmentation VLAN/firewall (une règle par port), contrairement à
un routage par IP source qui dérive (DHCP) ou collisionne (NAT). L'IP source
reste exploitée comme *allowlist de sécurité* par binding, pas comme clé de
routage.

``AnalyzerKind`` est le discriminateur inscrit dans chaque trame poussée sur
Redis ; ``AnalyzerParserFactory`` (cf. ``factory.py``) s'en sert pour choisir
le parseur lors du dépilage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.config import Settings


class AnalyzerKind(StrEnum):
    """Famille d'automate — sert de discriminateur de routage et de parseur."""

    HEMATOLOGY = "dymind_hematology"  # Dymind DH36 (hématologie)
    BIOCHEMISTRY = "dymind_biochemistry"  # Dymind (biochimie / coagulation)
    IMMUNO = "anbio_immuno"  # Anbio Bioscann (immunofluorescence)


@dataclass(frozen=True)
class AnalyzerBinding:
    """Paramètres d'un listener TCP dédié à un automate."""

    kind: AnalyzerKind
    host: str
    port: int
    ack_mode: str = "ack"
    allowed_ips: list[str] = field(default_factory=list)
    enabled: bool = True


def default_bindings(settings: Settings) -> list[AnalyzerBinding]:
    """Construit les bindings à partir de la configuration.

    Chaque automate a son port (9000/9001/9002 par défaut). L'hôte et
    l'allowlist sont partagés (VLAN unique) mais peuvent être surchargés par
    automate côté déploiement si besoin.
    """
    host = settings.ANALYZER_RAW_LISTENER_HOST
    allowed = list(settings.ANALYZER_ALLOWED_IPS)
    ack_mode = settings.ANALYZER_RAW_ACK_MODE
    return [
        AnalyzerBinding(
            kind=AnalyzerKind.HEMATOLOGY,
            host=host,
            port=settings.ANALYZER_HEMATOLOGY_PORT,
            ack_mode=ack_mode,
            allowed_ips=allowed,
            enabled=settings.ANALYZER_HEMATOLOGY_ENABLED,
        ),
        AnalyzerBinding(
            kind=AnalyzerKind.BIOCHEMISTRY,
            host=host,
            port=settings.ANALYZER_BIOCHEMISTRY_PORT,
            ack_mode=ack_mode,
            allowed_ips=allowed,
            enabled=settings.ANALYZER_BIOCHEMISTRY_ENABLED,
        ),
        AnalyzerBinding(
            kind=AnalyzerKind.IMMUNO,
            host=host,
            port=settings.ANALYZER_IMMUNO_PORT,
            ack_mode=ack_mode,
            allowed_ips=allowed,
            enabled=settings.ANALYZER_IMMUNO_ENABLED,
        ),
    ]


def enabled_bindings(settings: Settings) -> list[AnalyzerBinding]:
    """Bindings activés uniquement, avec garde-fou contre les ports en double."""
    bindings = [b for b in default_bindings(settings) if b.enabled]
    seen: dict[int, AnalyzerKind] = {}
    for binding in bindings:
        if binding.port in seen:
            raise ValueError(
                f"Port {binding.port} partagé par {seen[binding.port].value} et "
                f"{binding.kind.value} : chaque automate doit avoir un port distinct."
            )
        seen[binding.port] = binding.kind
    return bindings
