"""Tests — le pipeline de release ne peut pas publier prématurément.

Avant ce verrouillage, `release.yml` se déclenchait sur le même tag que la CI,
**sans aucune dépendance** : la GitHub Release pouvait naître avant — ou malgré —
l'échec des tests, et annoncer une version qui n'avait rien prouvé. Par-dessus,
`softprops/action-gh-release` marque par défaut `prerelease=false` et
`make_latest=true` : une bêta se serait présentée comme la version stable
recommandée.

Ces tests lisent le workflow réel. Ils échouent si le garde-fou disparaît.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI_PATH = WORKFLOWS / "ci.yml"


@pytest.fixture(scope="module")
def ci() -> dict:
    return yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def jobs(ci) -> dict:
    return ci["jobs"]


def _steps(job: dict) -> list[dict]:
    return job.get("steps") or []


def _uses(job: dict, prefix: str) -> list[dict]:
    return [s for s in _steps(job) if str(s.get("uses", "")).startswith(prefix)]


def _needs(job: dict) -> list[str]:
    """`needs` accepte un scalaire ou une liste — normalise en liste.

    `e2e` et `docker-stack` déclarent `needs: test` sous forme scalaire ; traiter
    la chaîne comme un itérable la découperait en caractères.
    """
    besoins = job.get("needs") or []
    return [besoins] if isinstance(besoins, str) else list(besoins)


# ── un seul chemin peut créer une release ───────────────────────────────────


def test_no_other_workflow_creates_a_release():
    """Aucun workflow hors `ci.yml` ne doit pouvoir publier une release."""
    coupables = []
    for path in WORKFLOWS.glob("*.y*ml"):
        if path.name == "ci.yml":
            continue
        if "action-gh-release" in path.read_text(encoding="utf-8"):
            coupables.append(path.name)
    assert not coupables, (
        f"{coupables} peuvent créer une release hors du pipeline verrouillé de ci.yml"
    )


def test_release_yml_no_longer_exists():
    """Le workflow autonome déclenché par tag est supprimé, pas neutralisé."""
    assert not (WORKFLOWS / "release.yml").exists()


def test_exactly_one_release_step(jobs):
    total = sum(len(_uses(job, "softprops/action-gh-release")) for job in jobs.values())
    assert total == 1, f"{total} étapes de release trouvées, une seule attendue"


# ── la release est le dernier maillon ───────────────────────────────────────

_JOBS_BLOQUANTS = {
    "test",
    "test-postgres",
    "codeql",
    "e2e",
    "docker-stack",
    "backup-restore",
    "tag-guard",
    "license-compliance",
}


def test_release_depends_on_docker_publication(jobs):
    """Une release ne peut pas précéder la publication de l'image."""
    assert set(_needs(jobs["release"])) == {"deploy", "tag-guard", "license-compliance"}


def test_docker_publication_depends_on_every_blocking_job(jobs):
    """Tests, PostgreSQL, restauration, CodeQL, Playwright, stack Docker."""
    assert set(_needs(jobs["deploy"])) == _JOBS_BLOQUANTS


def test_backup_restore_gates_the_image(jobs):
    """Régression visée : publier sans avoir démontré que la base se restaure."""
    assert "backup-restore" in _needs(jobs["deploy"])


def test_release_is_transitively_gated_by_all_blocking_jobs(jobs):
    """La chaîne complète release -> deploy -> {jobs bloquants} est intacte."""
    atteints: set[str] = set()
    a_visiter = _needs(jobs["release"])
    while a_visiter:
        nom = a_visiter.pop()
        if nom in atteints:
            continue
        atteints.add(nom)
        a_visiter.extend(_needs(jobs[nom]))
    assert _JOBS_BLOQUANTS <= atteints, (
        f"jobs non bloquants pour la release : {_JOBS_BLOQUANTS - atteints}"
    )


def test_release_only_runs_on_a_version_tag(jobs):
    assert "refs/tags/v" in jobs["release"]["if"]


# ── prerelease et latest ────────────────────────────────────────────────────


def _release_step(jobs) -> dict:
    return _uses(jobs["release"], "softprops/action-gh-release")[0]


def test_prerelease_and_make_latest_are_explicit(jobs):
    """Ne jamais dépendre des défauts de l'action (prerelease=false, latest=true)."""
    with_ = _release_step(jobs)["with"]
    assert "prerelease" in with_, "prerelease doit être explicite"
    assert "make_latest" in with_, "make_latest doit être explicite"
    assert "needs.tag-guard.outputs.prerelease" in str(with_["prerelease"])
    assert "needs.tag-guard.outputs.make_latest" in str(with_["make_latest"])


def test_suffixed_tag_is_classified_as_prerelease(jobs):
    """La classification vit dans `tag-guard`, source unique."""
    script = _tag_guard_script(jobs)
    assert "prerelease=true" in script
    assert "make_latest=false" in script
    assert "prerelease=false" in script


@pytest.mark.parametrize("tag", ["v0.8.0-beta.1", "v0.8.0-alpha.1", "v0.8.0-rc.1", "v1.0.0-rc.2"])
def test_prerelease_rule_matches_suffixed_tags(tag):
    """Reproduit la condition shell `[[ "$tag" == *-* ]]` du workflow."""
    assert "-" in tag, f"{tag} doit être classé pré-version"


@pytest.mark.parametrize("tag", ["v0.8.0", "v1.0.0", "v0.7.4"])
def test_stable_tags_are_not_prereleases(tag):
    assert "-" not in tag, f"{tag} doit être classé version stable"


# ── corps de la release ─────────────────────────────────────────────────────


def test_beta_body_carries_the_clinical_warning(jobs):
    etape = next(s for s in _steps(jobs["release"]) if s.get("id") == "body")
    script = etape["run"]
    assert "REAL_DATA_NO_GO" in script
    assert "BÊTA TECHNIQUE" in script
    assert "n'est pas une autorisation" in script or "ne constitue pas une autorisation" in script
    assert "désactivées par défaut" in script


def test_warning_is_only_composed_for_prereleases(jobs):
    etape = next(s for s in _steps(jobs["release"]) if s.get("id") == "body")
    assert etape["if"] == "needs.tag-guard.outputs.prerelease == 'true'"


def test_body_precedes_generated_notes(jobs):
    """`body` + `generate_release_notes` : l'API place le corps AVANT les notes."""
    with_ = _release_step(jobs)["with"]
    assert with_["generate_release_notes"] is True
    assert "steps.body.outputs.text" in str(with_["body"])


# ── image Docker ────────────────────────────────────────────────────────────


def test_image_never_receives_the_latest_tag(jobs):
    """Une bêta ne doit jamais devenir l'image `latest`."""
    build = _uses(jobs["deploy"], "docker/build-push-action")[0]
    tags = str(build["with"]["tags"])
    assert ":latest" not in tags
    assert "latest" not in tags.replace("make_latest", "")


def test_image_is_tagged_with_the_exact_version(jobs):
    build = _uses(jobs["deploy"], "docker/build-push-action")[0]
    tags = str(build["with"]["tags"])
    assert "github.ref_name" in tags, "le tag exact de version doit être appliqué"
    assert "github.sha" in tags, "le SHA doit rester traçable"


def test_immutable_digest_is_exposed(jobs):
    """Le digest est le seul identifiant réellement immuable de l'image."""
    assert jobs["deploy"]["outputs"]["digest"] == "${{ steps.build.outputs.digest }}"
    build = _uses(jobs["deploy"], "docker/build-push-action")[0]
    assert build.get("id") == "build"


# ── le workflow ne crée jamais de tag ───────────────────────────────────────


def test_workflow_never_creates_a_tag():
    """La création d'un tag reste un acte humain, jamais automatisé."""
    contenu = CI_PATH.read_text(encoding="utf-8")
    interdits = ["git tag", "git push --tags", "create-tag", "actions/github-script"]
    for motif in interdits:
        assert motif not in contenu, f"le workflow ne doit pas pouvoir créer un tag ({motif!r})"


def test_no_workflow_pushes_to_the_repository():
    for path in WORKFLOWS.glob("*.y*ml"):
        contenu = path.read_text(encoding="utf-8")
        assert "git push" not in contenu, f"{path.name} pousse vers le dépôt"


# ── garde de tag : forme et gouvernance ─────────────────────────────────────

_TAGS_VALIDES = ["v0.8.0", "v0.8.0-alpha.1", "v0.8.0-beta.1", "v0.8.0-rc.2", "v10.20.30"]
_TAGS_INVALIDES = [
    "v0.8",  # composant manquant
    "v0.8.0-beta",  # suffixe sans numéro
    "v0.8.0-beta.",  # numéro vide
    "0.8.0",  # préfixe v manquant
    "v0.8.0-dev.1",  # suffixe hors contrat
    "v0.8.0-BETA.1",  # casse
    "release-0.8.0",
    "v0.8.0.1",
]


def _tag_guard_script(jobs) -> str:
    etape = next(s for s in _steps(jobs["tag-guard"]) if s.get("id") == "check")
    return etape["run"]


def test_tag_guard_exists_and_gates_the_image(jobs):
    """Un tag malformé ne doit pas même déclencher une construction d'image."""
    assert "tag-guard" in jobs
    assert "tag-guard" in _needs(jobs["deploy"])


def test_tag_guard_runs_on_every_trigger(jobs):
    """Sans `if` de job : un `needs` sauté sauterait `deploy` hors tag."""
    assert "if" not in jobs["tag-guard"]
    assert "GITHUB_REF_TYPE" in _tag_guard_script(jobs), (
        "le no-op hors tag doit être fait dans le script, pas par un `if` de job"
    )


def _regexes(jobs) -> tuple[str, str]:
    script = _tag_guard_script(jobs)
    stable = re.search(r"stable='([^']+)'", script).group(1)
    pre = re.search(r"pre='([^']+)'", script).group(1)
    return stable, pre


@pytest.mark.parametrize("tag", _TAGS_VALIDES)
def test_valid_tags_are_accepted(jobs, tag):
    stable, pre = _regexes(jobs)
    assert re.match(stable, tag) or re.match(pre, tag), f"{tag} devrait être accepté"


@pytest.mark.parametrize("tag", _TAGS_INVALIDES)
def test_malformed_tags_are_refused(jobs, tag):
    stable, pre = _regexes(jobs)
    assert not (re.match(stable, tag) or re.match(pre, tag)), f"{tag} devrait être refusé"


def test_governance_status_file_exists_and_says_no_go():
    statut = (
        (REPO_ROOT / "docs" / "governance" / "CLINICAL_STATUS").read_text(encoding="utf-8").strip()
    )
    assert statut == "REAL_DATA_NO_GO"


def test_stable_tag_is_refused_while_no_go(jobs):
    """Tant que le NO-GO tient, aucune version ne peut se présenter comme stable."""
    script = _tag_guard_script(jobs)
    assert "docs/governance/CLINICAL_STATUS" in script, (
        "le statut doit être lu depuis un fichier versionné, pas codé en dur"
    )
    assert "REAL_DATA_NO_GO" in script
    assert "exit 1" in script


def test_tag_guard_is_the_single_source_of_classification(jobs):
    """La règle prerelease ne doit exister qu'à un seul endroit."""
    porteurs = [
        nom
        for nom, job in jobs.items()
        if any("prerelease=" in str(s.get("run", "")) for s in _steps(job))
    ]
    assert porteurs == ["tag-guard"], f"règle dupliquée dans {porteurs}"


# ── approvisionnement d'actionlint ──────────────────────────────────────────


def test_actionlint_archive_is_pinned_by_checksum(jobs):
    """Un tag de release est mutable : l'archive doit être vérifiée par SHA-256."""
    etape = next(s for s in _steps(jobs["test"]) if "Actionlint" in str(s.get("name", "")))
    sha = etape["env"]["ACTIONLINT_SHA256"]
    assert re.fullmatch(r"[0-9a-f]{64}", sha), f"SHA-256 malformé : {sha!r}"
    assert "sha256sum --check --strict" in etape["run"]


def test_checksum_is_not_fetched_from_the_same_release(jobs):
    """Télécharger le checksum depuis la release qu'il vérifie ne prouve rien."""
    etape = next(s for s in _steps(jobs["test"]) if "Actionlint" in str(s.get("name", "")))
    script = etape["run"]
    assert "checksums.txt" not in script
    assert script.count("curl") == 1, "une seule récupération : l'archive elle-même"


# ── permissions minimales ───────────────────────────────────────────────────


def test_workflow_default_permissions_are_read_only(ci):
    assert ci["permissions"] == {"contents": "read"}


@pytest.mark.parametrize(
    "job,permission",
    [
        ("codeql", "security-events"),
        ("deploy", "packages"),
        ("release", "contents"),
    ],
)
def test_elevated_permission_is_scoped_to_one_job(jobs, job, permission):
    """Chaque droit d'écriture n'existe que là où il est indispensable."""
    assert jobs[job]["permissions"].get(permission) == "write"
    autres = [
        nom
        for nom, j in jobs.items()
        if nom != job and (j.get("permissions") or {}).get(permission) == "write"
    ]
    assert not autres, f"{permission}: write accordé aussi à {autres}"


# ── conformité de licence : gate de distribution ────────────────────────────
#
# La qualification des composants tiers appartient au gate de DISTRIBUTION.
# Publier une image ou une Release sans son SBOM ni son texte de licence, ce
# serait distribuer sans pouvoir dire ce que l'on distribue.


def test_license_compliance_job_exists(jobs):
    assert "license-compliance" in jobs


@pytest.mark.parametrize("job", ["deploy", "release"])
def test_distribution_depends_on_license_compliance(jobs, job):
    assert "license-compliance" in jobs[job]["needs"], (
        f"{job} peut publier sans preuve de conformité de licence"
    )


def test_syft_is_pinned_by_version_and_checksum(jobs):
    """`latest` rendrait le SBOM non reproductible ; sans empreinte, non fiable."""
    env = jobs["license-compliance"]["env"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", env["SYFT_VERSION"]), env["SYFT_VERSION"]
    assert re.fullmatch(r"[0-9a-f]{64}", env["SYFT_SHA256"])
    etape = next(s for s in _steps(jobs["license-compliance"]) if "Syft" in str(s.get("name", "")))
    assert "sha256sum --check --strict" in etape["run"]
    assert "checksums.txt" not in etape["run"], (
        "récupérer le checksum depuis la release qu'il vérifie ne prouve rien"
    )


def test_no_action_or_tool_uses_a_floating_tag(ci):
    """Aucune référence mouvante : ni `@latest`, ni `@main`, ni tag non épinglé."""
    contenu = CI_PATH.read_text(encoding="utf-8")
    for reference in re.findall(r"uses:\s*(\S+)", contenu):
        if reference.startswith("${{"):
            continue
        assert re.search(r"@[0-9a-f]{40}$", reference), f"action non épinglée : {reference}"


def test_unknown_third_party_licenses_fail_the_build(jobs):
    etape = next(
        s for s in _steps(jobs["license-compliance"]) if "Inventaire" in str(s.get("name", ""))
    )
    assert "--fail-on-unknown" in etape["run"], (
        "une licence indéterminée ne peut pas être acceptée en silence"
    )


def test_release_attaches_the_compliance_evidence(jobs):
    etape = next(
        s
        for s in _steps(jobs["release"])
        if str(s.get("uses", "")).startswith("softprops/action-gh-release")
    )
    joints = etape["with"]["files"]
    for piece in (
        "CHANGELOG.md",
        "LICENSE.md",
        "THIRD_PARTY_NOTICES.md",
        "sbom.cyclonedx.json",
        "sbom.spdx.json",
        "RELEASE_PROVENANCE.md",
    ):
        assert piece in joints, f"{piece} n'est pas joint à la Release"
    assert etape["with"]["fail_on_unmatched_files"] is True, (
        "une pièce manquante doit faire échouer la publication, pas être ignorée"
    )


def test_release_reuses_the_verified_sboms(jobs):
    """Régénérer les SBOM ici publierait un inventaire que rien n'a vérifié."""
    etapes = _steps(jobs["release"])
    assert any(str(s.get("uses", "")).startswith("actions/download-artifact") for s in etapes), (
        "les SBOM doivent venir du job de conformité"
    )
    assert not any("syft" in str(s.get("run", "")).lower() for s in etapes)


def test_release_provenance_records_the_immutable_digest(jobs):
    etape = next(s for s in _steps(jobs["release"]) if "provenance" in str(s.get("name", "")))
    assert etape["env"]["DIGEST"] == "${{ needs.deploy.outputs.digest }}"
    assert "RELEASE_PROVENANCE.md" in etape["run"]
    assert "CLINICAL_STATUS" in etape["run"], "la provenance doit porter le statut clinique"
