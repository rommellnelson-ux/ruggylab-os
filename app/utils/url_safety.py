"""Garde anti-SSRF pour les URL de webhook contrôlées par l'utilisateur.

Empêche le serveur d'émettre des requêtes vers le réseau interne :
loopback, adresses privées (RFC 1918), link-local, et l'IP de métadonnées
cloud (169.254.169.254). N'autorise que les schémas http/https.

La résolution DNS est tentée pour bloquer les noms d'hôtes qui pointent vers
des adresses internes. En cas d'échec de résolution, l'URL est considérée
comme non sûre (on ne peut pas prouver qu'elle est externe).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTNAMES = {"localhost", "ip6-localhost", "ip6-loopback"}


def _ip_is_safe(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_external_url(url: str | None) -> bool:
    """Retourne True si l'URL est un endpoint http/https externe sûr."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False
    host = parsed.hostname
    if not host or host.lower() in _BLOCKED_HOSTNAMES:
        return False

    # Hôte fourni en littéral IP → vérification directe
    try:
        ipaddress.ip_address(host)
        return _ip_is_safe(host)
    except ValueError:
        pass  # ce n'est pas une IP littérale → résolution DNS

    # Résolution DNS : toutes les adresses retournées doivent être externes
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, OSError, UnicodeError):
        return False
    if not infos:
        return False
    return all(_ip_is_safe(info[4][0]) for info in infos)
