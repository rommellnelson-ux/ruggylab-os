# Preuve acceptée — baseline de qualité G0 (lot C)

> **INTERNAL — SECURITY ARCHITECTURE**
> **BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT**
>
> Ce répertoire décrit une mesure de référence, pas une installation. Il ne
> contient aucune adresse IP réelle de site, aucun identifiant, aucun secret,
> aucune donnée patient. Ce bandeau est une **mention de classification, pas un
> contrôle d'accès** : le seul contrôle réel serait la visibilité du dépôt.

```
status                 = ACCEPTED
evidence_type          = G0_QUALITY_BASELINE
measurement_source_sha = 02795a81b801b784572089d6a7860ba889d10a4c
review_date_utc        = 2026-09-13
```

## 1. Ce que ce répertoire est

Une **preuve historique immuable**. Il fige les cinq artefacts d'une campagne de
mesure précise, exécutée sur le commit `02795a8`, et de quoi vérifier que les
fichiers qu'on lit sont bien ceux qu'elle a produits.

Il existe parce que les artefacts de GitHub Actions **expirent** (90 jours).
Passé ce délai, le run `34786598282` restera consultable mais ses fichiers
auront disparu. Ce répertoire, lui, reste.

## 2. Ce que ce répertoire n'est pas

> **Ce n'est pas une valeur attendue.** Ne comparez **jamais** une campagne
> future à celle-ci octet par octet, ni latence par latence.

Deux exécutions de la même suite, sur la même révision, ne donnent pas les mêmes
chiffres. Entre la campagne `6afe098` et celle-ci, le débit à concurrence 1 est
passé de 48 à 65 req/s **sans qu'une ligne de code applicatif change** : le
runner GitHub était simplement plus rapide. Un contrôle qui exigerait de
retrouver ces nombres échouerait presque toujours, et serait donc désactivé —
puis la baseline ne vaudrait plus rien.

**Une campagne future se compare sur la méthode**, pas sur les chiffres :

- même plan de mesure (`measurement_plan_sha256`) ;
- même scénario (`scenario_sha256`) ;
- mêmes contrôles de validité, tous verts ;
- puis la **forme** des courbes — plateau de débit, croissance des latences,
  seuil d'apparition des erreurs.

C'est la forme qui se reproduit d'une campagne à l'autre, pas les valeurs.

## 3. Ce que l'acceptation signifie, et ne signifie pas

L'acceptation porte sur la **validité de la preuve** : la mesure dit ce qu'elle
prétend dire, sur le code qu'elle prétend décrire.

Elle ne dit **rien** de l'aptitude du produit à un usage clinique :

```
G0_PASS            = NON
REAL_DATA_GO       = NON
SITE_PRODUCTION_GO = NON
DISTRIBUTION_GO    = NON
```

Les constats défavorables de la campagne **restent ouverts** et sont énumérés
dans `EVIDENCE_MANIFEST.json` (`open_findings`) :

| Constat | Gravité |
| --- | --- |
| `CSA_SITE_PRODUCTION_GO_BLOCKER` | P1 |
| `INVOICE_CONCURRENCY_REMEDIATION_REQUIRED` | P1 |
| `PERFORMANCE_BOTTLENECK_PROFILING_REQUIRED` | P1 |
| `SITE_OPERATIONAL_PROFILE_REQUIRED` | P1 |
| `AUTH_CONCURRENCY_INVESTIGATION_REQUIRED` | P2 |

> **Le profil du site n'est pas mesuré.** Cette campagne tourne **limiteurs de
> débit désactivés**, pour mesurer la capacité intrinsèque du cœur. Le débit
> publié n'est pas atteignable en exploitation : le limiteur plafonne le débit
> soutenu à environ 1,7 requête par seconde **et par adresse IP**, et tous les
> postes d'un laboratoire derrière un même proxy partagent cette adresse. Une
> campagne distincte, avec limiteurs actifs et profil réseau du site, reste
> **obligatoire avant tout pilote réel**.

Aucune signature n'est apposée ni simulée. L'acceptation est consignée comme un
fait de gouvernance.

## 4. Contenu

| Fichier | Forme | Taille |
| --- | --- | ---: |
| `coverage.xml.gz` | gzip déterministe | 36 684 o |
| `coverage.json.gz` | gzip déterministe | 80 750 o |
| `coverage-summary.json` | brut, octet pour octet | 115 181 o |
| `perf-baseline.json` | brut, octet pour octet | 74 781 o |
| `perf-provenance.json` | brut, octet pour octet | 4 957 o |
| `EVIDENCE_MANIFEST.json` | manifeste | — |
| `README.md` | ce fichier | — |

Les trois JSON sont conservés **non compressés et non reformatés** : leur SHA-256
versionné est donc exactement celui de l'artefact d'origine, et une vérification
ne demande aucune étape intermédiaire.

## 5. Vérifier ces fichiers

**Les trois JSON** — le SHA doit être identique à `original_sha256` *et* à
`stored_sha256` dans le manifeste :

```bash
sha256sum coverage-summary.json perf-baseline.json perf-provenance.json
```

**Les deux fichiers compressés** — décompresser, puis comparer à
`original_sha256` :

```bash
gzip -dc coverage.xml.gz  | sha256sum   # 6ae1c4adaab833f8...
gzip -dc coverage.json.gz | sha256sum   # 0783264973b75a50...
```

**Tout d'un coup**, en s'appuyant sur le manifeste plutôt que sur des valeurs
recopiées à la main :

```bash
python - <<'PY'
import gzip, hashlib, json, pathlib
manifeste = json.loads(pathlib.Path("EVIDENCE_MANIFEST.json").read_text(encoding="utf-8"))
for entree in manifeste["files"]:
    octets = pathlib.Path(entree["stored_name"]).read_bytes()
    assert hashlib.sha256(octets).hexdigest() == entree["stored_sha256"], entree["stored_name"]
    if entree["compression"] == "gzip":
        octets = gzip.decompress(octets)
    assert hashlib.sha256(octets).hexdigest() == entree["original_sha256"], entree["original_name"]
    print(f"{entree['original_name']:24} OK")
PY
```

La compression est **déterministe** (gzip niveau 9, `mtime = 0`, aucun nom de
fichier stocké — équivalent de `gzip -n -9`). Recompresser le fichier d'origine
redonne exactement le même `.gz`.

## 6. Retrouver la campagne

| | |
| --- | --- |
| Commit mesuré | `02795a81b801b784572089d6a7860ba889d10a4c` |
| Base | `981ef356759bad628898fed0094c0dd40c8a7b57` |
| Arbre mesuré | `2097ecf8208af88253c8d1b596d9cc3ac7b9007d` |
| Fusion synthétique GitHub | `cde576af9c3a6386a1d208d8d560b90acb905aad` |
| Exécution | [`34786598282`](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/34786598282) |
| Job — couverture | `103803101950` |
| Job — performance | `103803102185` |

> `tested_merge_sha` est le commit de fusion **synthétique** que GitHub fabrique
> pour un événement `pull_request`. Ce n'est la tête d'aucune référence : le
> commit à retrouver est `measurement_source_sha`.

Les mêmes identités sont **embarquées dans les artefacts eux-mêmes**
(`measurement_identity`), de sorte qu'un lecteur d'un seul fichier sache sur quoi
la mesure a porté. À ne pas confondre avec `baseline_input_commit`, présent dans
`perf-provenance.json` : celui-ci est l'**ancrage historique déclaré** du
programme G0, pas le commit mesuré.

## 7. Ce répertoire n'influence aucune mesure

Il est **hors** des ensembles d'entrée `coverage` et `performance` de
`scripts/g0_provenance.py`. S'il y entrait, archiver une campagne changerait
l'empreinte de la suivante : la preuve modifierait ce qu'elle est censée
décrire. Les deux empreintes sont vérifiées identiques avant et après son ajout.

Les sorties courantes (`artifacts/g0/coverage.xml`, `coverage.json`,
`coverage-summary.json`, `perf-baseline.json`, `perf-provenance.json`) restent
ignorées par Git. Une nouvelle campagne locale ne touche donc pas ce répertoire.
