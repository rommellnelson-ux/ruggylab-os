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
QUALITY_BASELINE_CANDIDATE = REVIEW_PENDING
```

**Ce document ne prononce pas `QUALITY_BASELINE_ACCEPTED`.** Une baseline ne
devient acceptée qu'après revue indépendante, et c'est cette revue — pas
l'auteur de la mesure — qui décide. Tant que le statut ci-dessus n'a pas changé
de main, rien ici n'est acquis.

## 1. Ce qu'est ce document

Une campagne de mesure est un objet périssable : deux exécutions de la même
suite sur la même révision ne donnent pas les mêmes latences. On ne peut donc
pas versionner ses résultats et les comparer octet à octet — ce serait une
preuve que rien ne pourrait jamais contredire.

Ce manifeste fait l'inverse : il **désigne** une exécution précise, avec de quoi
la retrouver et de quoi vérifier que les fichiers qu'on lit sont bien ceux
qu'elle a produits. Les artefacts eux-mêmes restent des artefacts de CI
(90 jours de rétention). Leur archivage durable sous
`artifacts/g0/accepted/quality/<measurement_source_sha>/` est une **étape
postérieure à la revue**, délibérément non faite ici.

## 2. Identités de la campagne

Six identités distinctes, et il faut les distinguer : sur un événement
`pull_request`, `GITHUB_SHA` ne désigne **pas** la tête de la branche mais le
commit de fusion synthétique que GitHub fabrique pour l'occasion. Les confondre
ferait citer par la campagne un commit qui n'existe sur aucune référence et que
personne ne retrouverait ensuite.

| Identité | Valeur |
| --- | --- |
| `measurement_source_sha` (**tête Q1**) | `6afe098ab21d8cbcaea161d5ae3b7d407003ad58` |
| `base_sha` | `981ef356759bad628898fed0094c0dd40c8a7b57` |
| `tested_merge_sha` (fusion synthétique GitHub) | `e847523087b1bbe6791170474ff6c94163ad1904` |
| `tested_tree_sha` | `170ca31e2171ffc6eaf09666959f742fce475585` |
| `workflow_run_id` | `34776027833` (tentative 1) |
| Job — couverture | `103774175365` |
| Job — performance | `103774175500` |

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
| `coverage.xml` | 580 152 o | `e38a7c2f28d1a93b9099c60c3b94562cef03f94483235af2334153b1f2ca37c2` |
| `coverage.json` | 1 359 014 o | `66a5c9b9515bb29d4eebc6efb893047d7ac99c29461771d150a152d9ba427c80` |
| `coverage-summary.json` | 114 314 o | `aec65fbf05e7ff93084f40dfb8b4d3cea24e9b77c97d63decdc956092b299c34` |
| `perf-baseline.json` | 67 932 o | `cfe967172f6708392bdfa4078edd820225ad5d3bae5c97bdfcb302a0b1b0af0d` |
| `perf-provenance.json` | 3 737 o | `98815c6be3851b993bdfc5580697250b629069234bc96111128fbf655b6b3635` |

## 4. Image mesurée

| | |
| --- | --- |
| `image_id` | `sha256:6490d477e98ebbe101b98d32c0648d3baa0f77548400308b13a368aad1318890` |
| SHA-256 de l'archive | `28bc7a84bf3ac3371031e6e7dbd7860438d68d62848c4a151dbf2c2908428411` |

L'archive est produite avec `gzip -n` : sans cela, son empreinte changerait à
chaque exécution à cause du seul horodatage, et ne dirait plus rien de l'image.

## 5. Empreintes d'entrée et plan de mesure

| Ensemble | Fichiers | Empreinte |
| --- | ---: | --- |
| `coverage` | 376 | `ff1aadec587ad9259098d0b2a961ddd6d1a5e3f2a360a7831db56d900f676861` |
| `performance` | 296 | `12f945c95bfd155f301962d02cd137b780457e204fc02887bcd2bacef4abc40a` |

Le **plan de mesure** [`scripts/g0_quality_plan.json`](../../scripts/g0_quality_plan.json)
entre dans les deux empreintes, et son propre SHA-256 est inscrit dans les deux
artefacts (`measurement_plan_sha256`). Les validateurs **refusent** une campagne
dont les paramètres s'écarteraient du plan : sans ce refus, le plan ne serait
qu'une intention, et une campagne réduite continuerait de le citer.

Empreinte du scénario de performance : `84e8e408aff36448…`
(`perf-baseline.json`, `run.scenario_sha256`). Elle change dès qu'un pas change
de route, d'ordre ou de nature — indépendamment de toute reformulation de commentaire.

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
QUALITY_BASELINE_CANDIDATE_READY
QUALITY_BASELINE_CANDIDATE     = REVIEW_PENDING
CLINICAL_STATUS                = REAL_DATA_NO_GO
DISTRIBUTION_STATUS            = DISTRIBUTION_NO_GO
```

Ni `QUALITY_BASELINE_ACCEPTED`, ni `G0_LOT_C_EVIDENCE_REVIEWED`, ni
`G0_LOT_C_MERGED` ne sont prononcés. La PR #150 reste ouverte et non fusionnée.
