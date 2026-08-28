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

_JOBS_BLOQUANTS = {"test", "test-postgres", "codeql", "e2e", "docker-stack", "backup-restore"}


def test_release_depends_on_docker_publication(jobs):
    """Une release ne peut pas précéder la publication de l'image."""
    assert _needs(jobs["release"]) == ["deploy"]


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
    assert "steps.kind.outputs.prerelease" in str(with_["prerelease"])
    assert "steps.kind.outputs.make_latest" in str(with_["make_latest"])


def test_suffixed_tag_is_classified_as_prerelease(jobs):
    """La règle de classement repose sur le suffixe SemVer."""
    etape = next(s for s in _steps(jobs["release"]) if s.get("id") == "kind")
    script = etape["run"]
    assert "*-*" in script, "le suffixe SemVer doit décider de la nature de la version"
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
    assert etape["if"] == "steps.kind.outputs.prerelease == 'true'"


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
