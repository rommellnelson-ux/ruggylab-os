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

# Cette liste est volontairement exhaustive : toute modification des gates de
# publication doit être déclarée ici, sinon le test échoue. C'est le but — un
# gate ajouté par mégarde, ou retiré lors d'une fusion, ne doit pas passer
# inaperçu.
_JOBS_BLOQUANTS = {
    "test",
    "test-postgres",
    "codeql",
    "e2e",
    "docker-stack",
    "backup-restore",
    # Publier l'image sans savoir quels paquets copyleft elle contient ni où
    # leurs sources se trouvent, ce serait distribuer sans preuve.
    "debian-source-evidence",
    # La distribuer sans son texte de licence ni les notices de ses composants
    # ne satisfait aucune obligation.
    "license-compliance",
    # Sans ce job, `deploy` n'aurait pas l'archive auditée à pousser.
    "build-candidate",
    "tag-guard",
}

#: Jobs qui tournent mais ne conditionnent PAS la publication du cœur.
_JOBS_NON_BLOQUANTS = {"monitoring-overlay"}


def test_release_depends_on_docker_publication(jobs):
    """Une release ne peut pas précéder la publication de l'image."""
    assert set(_needs(jobs["release"])) == {
        "deploy",
        "tag-guard",
        "license-compliance",
        # La release rattache les manifestes Debian : elle doit dépendre du job
        # qui les produit, sinon l'artefact serait absent au téléchargement.
        "debian-source-evidence",
    }


def test_docker_publication_depends_on_every_blocking_job(jobs):
    """Tests, PostgreSQL, restauration, CodeQL, Playwright, stack Docker."""
    assert set(_needs(jobs["deploy"])) == _JOBS_BLOQUANTS


def test_optional_jobs_never_gate_the_image(jobs):
    """Grafana est externe : un cœur sain ne dépend pas de lui."""
    besoins = set(_needs(jobs["deploy"]))
    assert not (besoins & _JOBS_NON_BLOQUANTS), (
        f"un job optionnel bloque la publication : {besoins & _JOBS_NON_BLOQUANTS}"
    )


def test_source_evidence_gates_the_image(jobs):
    """Régression visée : publier sans preuve des sources correspondantes."""
    assert "debian-source-evidence" in _needs(jobs["deploy"])


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


def _etape_de_publication(jobs) -> dict:
    """L'étape qui pousse l'image.

    `deploy` ne construit plus : il pousse l'archive auditée. Les garanties de
    tag se lisent donc sur ses commandes, non sur une action de construction.
    """
    return next(e for e in _steps(jobs["deploy"]) if "docker push" in str(e.get("run", "")))


def test_image_never_receives_the_latest_tag(jobs):
    """Une bêta ne doit jamais devenir l'image `latest`."""
    script = _etape_de_publication(jobs)["run"]
    assert ":latest" not in script
    assert "latest" not in script.replace("make_latest", "")


def test_image_is_tagged_with_the_exact_version(jobs):
    script = _etape_de_publication(jobs)["run"]
    assert "GITHUB_REF_NAME" in script, "le tag exact de version doit être appliqué"
    assert "GITHUB_SHA" in script, "le SHA doit rester traçable"


def test_immutable_digest_is_exposed(jobs):
    """Le digest est le seul identifiant réellement immuable de l'image."""
    assert jobs["deploy"]["outputs"]["digest"] == "${{ steps.build.outputs.digest }}"
    etape = _etape_de_publication(jobs)
    assert etape.get("id") == "build"
    assert "RepoDigests" in etape["run"], "le digest doit être relevé APRÈS la poussée"


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


def test_image_sbom_is_audited_for_unknown_licenses(jobs):
    """Le gate Python ne couvre pas la base système, que l'image distribue."""
    etape = next(
        s for s in _steps(jobs["license-compliance"]) if "Auditer le SBOM" in str(s.get("name", ""))
    )
    assert "audit_sbom_licenses.py" in etape["run"]
    assert "SBOM_LICENSE_EXCEPTIONS.json" in etape["run"]


def test_the_audit_runs_after_the_sboms_are_generated(jobs):
    noms = [str(s.get("name", "")) for s in _steps(jobs["license-compliance"])]
    generation = next(i for i, n in enumerate(noms) if "Générer les SBOM" in n)
    audit = next(i for i, n in enumerate(noms) if "Auditer le SBOM" in n)
    assert generation < audit, "auditer un SBOM avant de le produire ne prouve rien"


# ── les deux gates de conformité, et rien qui les contourne ─────────────────
#
# Perdre l'un des deux lors d'une fusion rouvrirait exactement le trou qu'il
# ferme. Ces tests nomment chacun explicitement plutôt que de se fier au
# comptage : un message d'échec doit dire lequel manque.


@pytest.mark.parametrize("gate", ["debian-source-evidence", "license-compliance"])
def test_both_compliance_gates_block_publication(jobs, gate):
    assert gate in _needs(jobs["deploy"]), f"gate de conformité perdu : {gate}"


def test_no_job_publishes_outside_the_gated_chain(jobs):
    """Toute publication passe par `deploy`, donc par les deux gates."""
    marqueurs = ("docker/build-push-action", "docker push", "action-gh-release")
    publiants = {
        nom
        for nom, job in jobs.items()
        if any(
            marqueur in str(etape.get("uses", "")) + str(etape.get("run", ""))
            for etape in _steps(job)
            for marqueur in marqueurs
        )
    }
    assert publiants <= {"deploy", "release"}, f"chemin de publication parallèle : {publiants}"


# ── le gate de DISTRIBUTION, distinct du gate clinique ──────────────────────


def test_the_distribution_status_file_exists_and_forbids_distribution():
    statut = (REPO_ROOT / "docs" / "governance" / "DISTRIBUTION_STATUS").read_text(encoding="utf-8")
    assert statut.strip() == "DISTRIBUTION_NO_GO"


def test_the_two_statuses_are_separate_files():
    """Un seul fichier laisserait croire que lever l'un lève l'autre."""
    clinique = REPO_ROOT / "docs" / "governance" / "CLINICAL_STATUS"
    distribution = REPO_ROOT / "docs" / "governance" / "DISTRIBUTION_STATUS"
    assert clinique.is_file() and distribution.is_file()
    assert clinique.read_text(encoding="utf-8").strip() == "REAL_DATA_NO_GO"
    assert clinique.read_text(encoding="utf-8") != distribution.read_text(encoding="utf-8")


def test_tag_guard_reads_the_distribution_status(jobs):
    etape = next(
        e for e in _steps(jobs["tag-guard"]) if "statut de gouvernance" in str(e.get("name", ""))
    )
    script = etape["run"]
    assert "DISTRIBUTION_STATUS" in script
    assert "CONTROLLED_EVALUATION_DISTRIBUTION_GO" in script


def test_a_well_formed_prerelease_is_refused_while_distribution_is_blocked(jobs):
    """Le contrôle de distribution passe AVANT l'examen de la forme du tag.

    Sans cela, une pré-version correctement formée serait acceptée : la forme du
    tag n'a rien à voir avec l'autorisation de distribuer.
    """
    etape = next(
        e for e in _steps(jobs["tag-guard"]) if "statut de gouvernance" in str(e.get("name", ""))
    )
    script = etape["run"]
    position_distribution = script.index("DISTRIBUTION_STATUS")
    position_forme = script.index("pre='^v")
    assert position_distribution < position_forme, (
        "le gate de distribution doit précéder l'examen de la forme du tag"
    )


# ── `workflow_dispatch` ne peut plus publier ────────────────────────────────


def test_manual_dispatch_cannot_publish_an_image(ci):
    """Il permettait de publier sans tag, donc sans passer par `tag-guard`."""
    condition = ci["jobs"]["deploy"].get("if", "")
    assert "workflow_dispatch" not in condition, (
        "un déclenchement manuel contournerait le gate de distribution"
    )
    assert "refs/tags/v" in condition


def test_release_also_requires_a_tag(ci):
    assert "refs/tags/v" in ci["jobs"]["release"].get("if", "")


# ── identité de l'artefact : construit une fois, audité, publié tel quel ────


def test_the_candidate_image_is_built_exactly_once(ci):
    """Deux constructions du même Dockerfile peuvent différer."""
    constructions = [
        (nom, etape.get("name"))
        for nom, job in ci["jobs"].items()
        for etape in (job.get("steps") or [])
        # `docker build -t` : la commande réelle. Une mention de « docker build »
        # dans un commentaire ou une métadonnée n'est pas une construction.
        if "docker build -t" in str(etape.get("run", ""))
    ]
    assert len(constructions) == 1, (
        f"l'image est construite {len(constructions)} fois : {constructions}"
    )
    assert constructions[0][0] == "build-candidate"


@pytest.mark.parametrize(
    "job",
    [
        "docker-stack",
        "monitoring-overlay",
        "license-compliance",
        "debian-source-evidence",
        "deploy",
    ],
)
def test_every_consumer_loads_the_candidate_instead_of_rebuilding(ci, job):
    besoins = ci["jobs"][job].get("needs", [])
    besoins = [besoins] if isinstance(besoins, str) else besoins
    assert "build-candidate" in besoins, f"{job} ne dépend pas de l'image candidate"
    etapes = ci["jobs"][job]["steps"]
    assert any(
        str(e.get("uses", "")).startswith("actions/download-artifact")
        and (e.get("with") or {}).get("name") == "candidate-image"
        for e in etapes
    ), f"{job} ne charge pas l'archive candidate"


@pytest.mark.parametrize(
    "job",
    [
        "docker-stack",
        "monitoring-overlay",
        "license-compliance",
        "debian-source-evidence",
        "deploy",
    ],
)
def test_every_consumer_verifies_the_identity_it_loaded(ci, job):
    """Charger une archive sans vérifier son identité ne prouve rien."""
    script = " ".join(str(e.get("run", "")) for e in ci["jobs"][job]["steps"])
    assert "outputs.image_id" in script, f"{job} ne compare pas l'image ID"
    assert "outputs.archive_sha256" in script, f"{job} ne compare pas l'empreinte de l'archive"


def test_deploy_pushes_without_rebuilding(ci):
    etapes = ci["jobs"]["deploy"]["steps"]
    script = " ".join(str(e.get("run", "")) for e in etapes)
    assert "docker push" in script
    assert "docker build -t" not in script, (
        "deploy reconstruit : l'image publiée ne serait pas celle qui a été auditée"
    )
    assert not any(str(e.get("uses", "")).startswith("docker/build-push-action") for e in etapes)


def test_the_identity_chain_is_recorded(ci):
    etape = next(
        e for e in ci["jobs"]["deploy"]["steps"] if "identity chain" in str(e.get("name", ""))
    )
    script = etape["run"]
    for element in ("image_id", "archive_sha256", "outputs.digest"):
        assert element in script, f"la provenance n'inscrit pas {element}"


def test_the_candidate_archive_never_reaches_a_registry(ci):
    """Sur une PR, l'artefact candidat reste interne à la CI."""
    etape = next(
        e
        for e in ci["jobs"]["build-candidate"]["steps"]
        if str(e.get("uses", "")).startswith("actions/upload-artifact")
    )
    assert (etape.get("with") or {}).get("name") == "candidate-image"
    script = " ".join(str(e.get("run", "")) for e in ci["jobs"]["build-candidate"]["steps"])
    assert "docker push" not in script and "ghcr.io" not in script


# ── les artefacts de la release viennent des gates, pas d'une régénération ──

_PIECES_ATTENDUES = (
    "CHANGELOG.md",
    "LICENSE.md",
    "THIRD_PARTY_NOTICES.md",
    "sbom.cyclonedx.json",
    "sbom.spdx.json",
    "python-licenses.json",
    "RELEASE_PROVENANCE.md",
    "ARTIFACT_IDENTITY.md",
    "debian-binary-packages.json",
    "debian-source-packages.json",
    "debian-license-manifest.json",
    "SOURCE_COMPLIANCE.md",
    "DEBIAN_NOTICE_EXCEPTIONS.json",
)


@pytest.mark.parametrize("piece", _PIECES_ATTENDUES)
def test_the_release_attaches_every_required_piece(jobs, piece):
    etape = next(
        e
        for e in _steps(jobs["release"])
        if str(e.get("uses", "")).startswith("softprops/action-gh-release")
    )
    assert piece in etape["with"]["files"], f"pièce absente de la Release : {piece}"


def test_the_release_regenerates_nothing(jobs):
    """Régénérer après les gates publierait des preuves que rien n'a validées."""
    script = " ".join(str(e.get("run", "")) for e in _steps(jobs["release"]))
    for interdit in ("syft", "python -m build", "docker build", "inventory_python_licenses"):
        assert interdit not in script, f"la release régénère : {interdit}"
    telecharges = {
        (e.get("with") or {}).get("name")
        for e in _steps(jobs["release"])
        if str(e.get("uses", "")).startswith("actions/download-artifact")
    }
    assert {"third-party-evidence", "debian-source-evidence", "artifact-identity"} <= telecharges


def test_docker_format_templates_are_well_formed(ci):
    """Un gabarit `--format` mal échappé fait échouer le job, pas le test.

    Les tests d'identité vérifiaient que le script COMPARE bien l'image ID ;
    aucun ne vérifiait que la commande qui le lit est syntaxiquement valide. Un
    échappement de trop — `{{{{.Id}}}}` au lieu de `{{.Id}}` — passait donc les
    tests et cassait quatre jobs en CI.
    """
    contenu = CI_PATH.read_text(encoding="utf-8")
    for gabarit in re.findall(r"--format\s+'([^']+)'", contenu):
        assert "{{{" not in gabarit, f"accolades en trop dans le gabarit Docker : {gabarit}"
        assert gabarit.count("{{") == gabarit.count("}}"), f"gabarit déséquilibré : {gabarit}"
        assert not re.search(r"\{\{\{|\}\}\}", gabarit), f"gabarit malformé : {gabarit}"
