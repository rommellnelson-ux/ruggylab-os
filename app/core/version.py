"""Source unique de la version de RuggyLab OS.

La version se décline en trois écritures qui doivent rester cohérentes, et qui
divergeaient jusqu'ici (`pyproject` disait `0.1.0`, `.env.example` `0.7.4`, le
dernier tag `v0.7.4`) :

===================  ==================  ==========================================
Écriture             Exemple             Où elle apparaît
===================  ==================  ==========================================
tag Git              ``v0.8.0-beta.1``   tag, image Docker, GitHub Release
version publique     ``0.8.0-beta.1``    API/OpenAPI, labels OCI, CHANGELOG
version PEP 440      ``0.8.0b1``         ``pyproject.toml`` (le paquet Python)
===================  ==================  ==========================================

PEP 440 n'admet pas ``0.8.0-beta.1`` : la forme normalisée est ``0.8.0b1``. Les
deux désignent la même version — c'est bien pourquoi elles doivent être dérivées
d'ici et vérifiées par un test, plutôt que recopiées à la main.
"""

from __future__ import annotations

#: Version publique, telle qu'annoncée à l'utilisateur et dans l'API.
VERSION = "0.8.0-beta.1"

#: Même version, normalisée pour les outils Python (``pyproject.toml``).
PEP440_VERSION = "0.8.0b1"

#: Tag Git correspondant.
GIT_TAG = f"v{VERSION}"

#: Vrai tant que la version porte un suffixe SemVer (alpha/beta/rc).
IS_PRERELEASE = "-" in VERSION
