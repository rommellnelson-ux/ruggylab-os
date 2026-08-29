"""Tests — aucune page n'appelle un service de polices tiers.

Une police chargée depuis un CDN crée trois problèmes à la fois : une requête
sortante depuis le poste client vers un tiers, une dépendance réseau qui casse
l'affichage en environnement contraint ou hors ligne, et une licence de police
à qualifier avant distribution. Une pile système supprime les trois.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Hôtes de services de polices dont dépendre est interdit.
_HOTES_INTERDITS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "use.typekit.net",
    "fonts.bunny.net",
    "cdn.jsdelivr.net/npm/@fontsource",
)

#: Fichiers servis au navigateur.
_GABARITS = sorted((REPO_ROOT / "app" / "templates").rglob("*.html"))
_STATIQUES = sorted(
    p for p in (REPO_ROOT / "app" / "static").rglob("*") if p.suffix in {".css", ".js", ".html"}
)


def _relatif(chemin: Path) -> str:
    return str(chemin.relative_to(REPO_ROOT)).replace("\\", "/")


@pytest.mark.parametrize("chemin", _GABARITS + _STATIQUES, ids=_relatif)
def test_no_external_font_service_is_referenced(chemin):
    contenu = chemin.read_text(encoding="utf-8", errors="replace")
    for hote in _HOTES_INTERDITS:
        assert hote not in contenu, (
            f"{_relatif(chemin)} appelle {hote} — la page ne fonctionnerait plus "
            "hors ligne, et la licence de la police resterait à qualifier"
        )


@pytest.mark.parametrize("chemin", _GABARITS, ids=_relatif)
def test_no_font_face_downloads_a_remote_file(chemin):
    """Une `@font-face` distante rétablirait la dépendance par un autre chemin."""
    contenu = chemin.read_text(encoding="utf-8", errors="replace")
    for bloc in re.findall(r"@font-face\s*\{[^}]*\}", contenu, re.DOTALL):
        for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", bloc):
            assert not url.startswith(("http://", "https://", "//")), (
                f"{_relatif(chemin)} : @font-face distante — {url}"
            )


# ── la carte EHM, seule page concernée, garde un rendu défini ───────────────

_CARTE = REPO_ROOT / "app" / "templates" / "ehm_map.html"


@pytest.fixture(scope="module")
def carte() -> str:
    return _CARTE.read_text(encoding="utf-8")


def test_the_map_declares_system_font_stacks(carte):
    assert "--font-sans:" in carte and "--font-mono:" in carte
    for repli in ("system-ui", "-apple-system", "Segoe UI", "sans-serif"):
        assert repli in carte, f"pile incomplète : {repli} absent"
    for repli in ("ui-monospace", "monospace"):
        assert repli in carte, f"pile monospace incomplète : {repli} absent"


def test_every_font_family_uses_the_declared_stacks(carte):
    """Aucune déclaration ne doit rester orpheline, sinon le rendu diverge."""
    declarations = re.findall(r"font-family:\s*([^;]+);", carte)
    assert declarations, "aucune déclaration de police trouvée"
    for valeur in declarations:
        valeur = valeur.strip()
        if valeur.startswith("var(--font-"):
            continue
        assert "sans-serif" in valeur or "monospace" in valeur, (
            f"déclaration sans repli générique : {valeur!r}"
        )


def test_no_font_file_was_vendored():
    """La bêta retient la pile système : aucune police n'est embarquée."""
    polices = [
        p
        for p in (REPO_ROOT / "app").rglob("*")
        if p.suffix.lower() in {".woff", ".woff2", ".ttf", ".otf", ".eot"}
    ]
    assert not polices, f"police embarquée alors que la décision est la pile système : {polices}"


# ── les autres ressources externes ne sont pas touchées par cette PR ────────


def test_leaflet_and_barcodes_are_untouched(carte):
    """Le périmètre est la police, pas la cartographie ni les codes-barres."""
    assert "leaflet.min.css" in carte and "leaflet.min.js" in carte
    assert "openstreetmap" in carte.lower(), "l'attribution OSM doit rester"
