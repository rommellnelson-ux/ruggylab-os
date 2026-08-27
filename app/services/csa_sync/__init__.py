"""Synchronisation CSA Plateau ↔ RuggyLab OS (laboratoire).

Ce paquet consomme le contrat d'interopérabilité exposé par la Supabase de
CSA Plateau : il *tire* (poll) les prescriptions d'examens et les transforme en
ordres d'examen RuggyLab (flux entrant, phase I1), et *pousse* les accusés de
réception. Le flux sortant (résultats → CSA) viendra en phase I2.

Tout est inactif tant que ``settings.CSA_SYNC_ENABLED`` est faux : aucun couplage,
aucun appel réseau au démarrage. Le worker tourne dans le process planificateur
(``PROCESS_ROLE=scheduler``), jamais dans les workers web.
"""

from __future__ import annotations

__all__ = ["exam_map", "client", "inbound", "state"]
