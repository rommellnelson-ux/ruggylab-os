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
QUALITY_BASELINE_CANDIDATE = MEASUREMENT_PENDING
```

> **Ce manifeste est dans son état d'attente.** Le commit qui le porte corrige
> les générateurs — version Valkey, identités embarquées — et **invalide donc
> la campagne précédente** : les artefacts qu'elle a produits ne sont plus ceux
> que ce code produit. Nommer encore cette campagne reviendrait à désigner des
> fichiers que plus aucune exécution ne reproduit.
>
> Les identités et les empreintes sont renseignées par le commit
> **documentaire** qui suit, une fois la nouvelle campagne exécutée et ses deux
> jobs verts.

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
| `measurement_source_sha` (**tête Q1**) | *à mesurer* |
| `base_sha` | `981ef356759bad628898fed0094c0dd40c8a7b57` |
| `tested_merge_sha` (fusion synthétique GitHub) | *à mesurer* |
| `tested_tree_sha` | *à mesurer* |
| `workflow_run_id` | *à mesurer* |
| Job — couverture | *à mesurer* |
| Job — performance | *à mesurer* |

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
| `coverage.xml` | *à mesurer* | *à mesurer* |
| `coverage.json` | *à mesurer* | *à mesurer* |
| `coverage-summary.json` | *à mesurer* | *à mesurer* |
| `perf-baseline.json` | *à mesurer* | *à mesurer* |
| `perf-provenance.json` | *à mesurer* | *à mesurer* |

## 4. Image mesurée

| | |
| --- | --- |
| `image_id` | *à mesurer* |
| SHA-256 de l'archive | *à mesurer* |

L'archive est produite avec `gzip -n` : sans cela, son empreinte changerait à
chaque exécution à cause du seul horodatage, et ne dirait plus rien de l'image.

## 5. Empreintes d'entrée et plan de mesure

| Ensemble | Fichiers | Empreinte |
| --- | ---: | --- |
| `coverage` | *à mesurer* | *à mesurer* |
| `performance` | *à mesurer* | *à mesurer* |

Le **plan de mesure** [`scripts/g0_quality_plan.json`](../../scripts/g0_quality_plan.json)
entre dans les deux empreintes, et son propre SHA-256 est inscrit dans les deux
artefacts (`measurement_plan_sha256`). Les validateurs **refusent** une campagne
dont les paramètres s'écarteraient du plan : sans ce refus, le plan ne serait
qu'une intention, et une campagne réduite continuerait de le citer.

Empreinte du scénario de performance : *à mesurer*
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
QUALITY_BASELINE_CANDIDATE     = MEASUREMENT_PENDING
CLINICAL_STATUS                = REAL_DATA_NO_GO
DISTRIBUTION_STATUS            = DISTRIBUTION_NO_GO
```

Ni `QUALITY_BASELINE_ACCEPTED`, ni `G0_LOT_C_EVIDENCE_REVIEWED`, ni
`G0_LOT_C_MERGED` ne sont prononcés. La PR #150 reste ouverte et non fusionnée.
