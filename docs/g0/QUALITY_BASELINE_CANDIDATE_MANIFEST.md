# G0 — Campagne candidate de qualité (lot C)

> **INTERNAL — SECURITY ARCHITECTURE**
> **BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT**
>
> Ce document décrit une architecture de référence, pas une installation. Il ne
> contient aucune adresse IP réelle de site, aucun identifiant, aucun secret,
> aucun nom de compte, aucune topologie VLAN réelle et aucune donnée patient —
> et il ne doit pas en recevoir tant que le dépôt reste public.
>
> Ce bandeau est une **mention de classification, pas un contrôle d'accès** : il
> n'empêche personne de lire ce fichier. Le seul contrôle réel serait la
> visibilité du dépôt.

```
QUALITY_BASELINE_ACCEPTED
G0_LOT_C_INDEPENDENT_REVIEW = ACCEPTED
review_date_utc             = 2026-09-13
```

La seconde revue indépendante a conclu à l'acceptation. La campagne est
archivée, immuable, sous
`artifacts/g0/accepted/quality/02795a81b801b784572089d6a7860ba889d10a4c/`.

> **L'acceptation porte sur la PREUVE, pas sur le produit.** Ni `G0_PASS`, ni
> `REAL_DATA_GO`, ni `SITE_PRODUCTION_GO`, ni `DISTRIBUTION_GO` ne sont
> prononcés, et les cinq constats défavorables de la campagne restent ouverts.
> Voir [`QUALITY_BASELINE_REVIEW_DECISION.md`](QUALITY_BASELINE_REVIEW_DECISION.md).

> **Deuxième campagne candidate.** La première a fait l'objet d'une revue
> indépendante concluant `CHANGES_REQUIRED` : version de produit Valkey fausse,
> causalité inférée présentée comme mesurée, décompte de jobs qui ne comptait
> pas des jobs. Les corrections touchent les **générateurs**, ce qui a invalidé
> la campagne précédente : ses artefacts ne sont plus ceux que ce code produit.
> Celle-ci est entièrement nouvelle — aucun hash, aucune identité n'a été
> reconduit.

## 1. Ce qu'est ce document

Une campagne de mesure est un objet périssable : deux exécutions de la même
suite sur la même révision ne donnent pas les mêmes latences. On ne peut donc
pas versionner ses résultats et les comparer octet à octet — ce serait une
preuve que rien ne pourrait jamais contredire.

Ce manifeste fait l'inverse : il **désigne** une exécution précise, avec de quoi
la retrouver et de quoi vérifier que les fichiers qu'on lit sont bien ceux
qu'elle a produits. Les artefacts eux-mêmes restent des artefacts de CI
(90 jours de rétention). Leur archivage durable sous
`artifacts/g0/accepted/quality/02795a81b801b784572089d6a7860ba889d10a4c/`
**existe désormais** : la revue a eu lieu, et les cinq artefacts y sont figés
avec leur manifeste d'intégrité.

## 2. Identités de la campagne

Six identités distinctes, et il faut les distinguer : sur un événement
`pull_request`, `GITHUB_SHA` ne désigne **pas** la tête de la branche mais le
commit de fusion synthétique que GitHub fabrique pour l'occasion. Les confondre
ferait citer par la campagne un commit qui n'existe sur aucune référence et que
personne ne retrouverait ensuite.

| Identité | Valeur |
| --- | --- |
| `measurement_source_sha` (**tête Q1**) | `02795a81b801b784572089d6a7860ba889d10a4c` |
| `base_sha` | `981ef356759bad628898fed0094c0dd40c8a7b57` |
| `tested_merge_sha` (fusion synthétique GitHub) | `cde576af9c3a6386a1d208d8d560b90acb905aad` |
| `tested_tree_sha` | `2097ecf8208af88253c8d1b596d9cc3ac7b9007d` |
| `workflow_run_id` | `34786598282` (tentative 1) |
| Job — couverture | `103803101950` |
| Job — performance | `103803102185` |

Ces six identités sont désormais **embarquées dans les artefacts eux-mêmes**
(`coverage-summary.json` et `perf-provenance.json`, champ
`measurement_identity`), et plus seulement consignées ici. Un lecteur du seul
artefact canonique sait donc sur quelle tête la mesure a porté, sans fichier
annexe ni acte de foi.

> **`measurement_source_sha` est la tête Q1, jamais le commit qui ajoutera le
> snapshot.** Nommer le répertoire d'après le commit qui le contient créerait
> une dépendance circulaire : le manifeste citerait un SHA qui n'existe pas
> encore au moment où on l'écrit.

Le commit **Q2** — celui qui porte ce document et les deux documents de
résultats — est distinct et postérieur. Il ne touche que des fichiers Markdown,
donc **aucune empreinte d'entrée** des ensembles `coverage` et `performance` :
une nouvelle exécution sur Q2 serait valide, et ces documents continueraient de
désigner Q1 comme campagne canonique.

## 3. Empreintes des cinq artefacts

SHA-256 des fichiers tels que la CI les a publiés, sur l'exécution ci-dessus.

| Artefact | Taille | SHA-256 |
| --- | ---: | --- |
| `coverage.xml` | 580 152 o | `6ae1c4adaab833f8672ded6ed48d38f977861f5f7683fc6b32bff955722b41f1` |
| `coverage.json` | 1 359 014 o | `0783264973b75a50e7d706690fe3027c17aa2def0ccf04460c9d931a7544baed` |
| `coverage-summary.json` | 115 181 o | `7cb103ae28955692cab9d4809979902f266424e45ae3b7dd833450fcfcc9cf25` |
| `perf-baseline.json` | 74 781 o | `6ee4b56f96df210105096d36e52d39f4ed775e2d3292457238006b160f7957fb` |
| `perf-provenance.json` | 4 957 o | `6800d71ae6204fad8428083ebb9988a7a9c68bb1d1ceda86083266b947e3a069` |

## 4. Image mesurée

| | |
| --- | --- |
| `image_id` | `sha256:1edab0d5f47374eed5bd0464c70e56f7e106d6bbd101d662bd7427b287fd92ee` |
| SHA-256 de l'archive | `a003354da1cfa00ddcf720bedbc4c64c8592b57f590d4929a1f2b37c7b0adef2` |

L'archive est produite avec `gzip -n` : sans cela, son empreinte changerait à
chaque exécution à cause du seul horodatage, et ne dirait plus rien de l'image.

## 5. Empreintes d'entrée et plan de mesure

| Ensemble | Fichiers | Empreinte |
| --- | ---: | --- |
| `coverage` | 376 | `ec6c08a6a1de44f22c932e13bc007d5210b6784d77d329ec5573dc297257931f` |
| `performance` | 296 | `9ecec37f7ce09e8e9e62b1056238b49d937b8dafbff81c0f9803a3b9bde04e43` |

Le **plan de mesure** [`scripts/g0_quality_plan.json`](../../scripts/g0_quality_plan.json)
entre dans les deux empreintes, et son propre SHA-256 est inscrit dans les deux
artefacts (`measurement_plan_sha256`). Les validateurs **refusent** une campagne
dont les paramètres s'écarteraient du plan : sans ce refus, le plan ne serait
qu'une intention, et une campagne réduite continuerait de le citer.

Empreinte du scénario de performance : `84e8e408aff36448…`
(`perf-baseline.json`, `run.scenario_sha256`). Elle change dès qu'un pas change
de route, d'ordre ou de nature — indépendamment de toute reformulation de commentaire.

## 5 bis. Décompte des jobs de CI

Décompte des **jobs** sur `02795a8`, produit par
[`scripts/g0_ci_job_report.py`](../../scripts/g0_ci_job_report.py) depuis l'API
GitHub — jamais saisi à la main :

| Workflow | Jobs | Détail |
| --- | ---: | --- |
| CI (run `34786598336`) | 15 | 13 `success` · 2 `skipped` |
| G0 Quality baseline (run `34786598282`) | 2 | 2 `success` |

**Total : 17 jobs.** Les deux `skipped` sont `Build and publish Docker image` et
`Publish GitHub Release`, sautés faute de tag — condition attendue.

> **Pourquoi ce décompte est généré.** La campagne précédente annonçait
> « 16 SUCCESS », chiffre pris dans `gh pr view --json statusCheckRollup`. Ce
> rollup agrège les *check runs* d'une tête, et CodeQL en publie un **en plus**
> de son job : 13 + 2 + 1 = 16. Le nombre était exact pour ce qu'il comptait, et
> faux pour ce qu'il prétendait décrire. Un chiffre juste, mal étiqueté — la
> forme la plus tenace d'erreur de preuve.

## 6. Ce que la campagne établit, et ce qu'elle n'établit pas

**Établi** — mesuré sur cette exécution, chiffres publiés tels qu'ils sortent :

- couverture de lignes et de branches de `app/**`, trois processus instrumentés
  combinés ;
- latences p50/p95/p99, débit et taux d'erreur à quatre niveaux de concurrence,
  sur la stack Docker réelle derrière le proxy TLS ;
- consommation CPU et mémoire **pendant** la fenêtre de charge, par conteneur.

**Non établi, et il faut le dire :**

```
PERFORMANCE_PROFILE = CORE_INTRINSIC_WITH_RATE_LIMITS_DISABLED
SITE_OPERATIONAL_PROFILE_REQUIRED
```

La campagne mesure la **capacité intrinsèque du cœur**, limiteurs de débit
désactivés. Elle ne décrit **pas** le comportement du futur site. Une campagne
distincte, obligatoire avant tout pilote réel, devra être conduite avec les
limiteurs actifs, Caddy, un `X-Forwarded-For` réel, `TRUSTED_PROXY_IPS`
configuré, trois clients représentatifs, la protection anti-force-brute active,
et l'absence de `429` sur un parcours normal. **Elle n'a pas été exécutée**, et
rien ici ne doit être lu comme si elle l'avait été.

## 7. Statut

```
QUALITY_BASELINE_ACCEPTED
G0_LOT_C_INDEPENDENT_REVIEW    = ACCEPTED
CLINICAL_STATUS                = REAL_DATA_NO_GO
DISTRIBUTION_STATUS            = DISTRIBUTION_NO_GO
```

Restent **non prononcés** : `G0_PASS`, `REAL_DATA_GO`, `SITE_PRODUCTION_GO`,
`DISTRIBUTION_GO`. Accepter une preuve n'est pas accepter un produit.
