# G0 — Baseline de performance (preuve 8)

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

> **Aucun objectif de latence.** Une latence élevée est un résultat, pas un
> échec. Le seul verdict que porte cette campagne concerne la **validité de la
> mesure** : une mesure dont on ne pourrait rien conclure fait échouer le job ;
> un chiffre déplaisant, jamais.
>
> Mesuré par la CI Linux (`.github/workflows/g0-quality.yml`, job
> **G0 — Performance baseline**) au moyen de
> [`scripts/g0_perf_baseline.py`](../../scripts/g0_perf_baseline.py).

> **Campagne acceptée.** La seconde revue indépendante a conclu
> `G0_LOT_C_INDEPENDENT_REVIEW = ACCEPTED` le 2026-09-13. Les cinq artefacts
> sont archivés, immuables, sous
> [`artifacts/g0/accepted/quality/02795a81b801b784572089d6a7860ba889d10a4c/`](../../artifacts/g0/accepted/quality/02795a81b801b784572089d6a7860ba889d10a4c/).
>
> L'acceptation porte sur la **validité de la preuve**, jamais sur l'aptitude du
> produit à la production clinique. Les constats défavorables restent ouverts —
> voir [`QUALITY_BASELINE_REVIEW_DECISION.md`](QUALITY_BASELINE_REVIEW_DECISION.md).
> Aucun seuil de couverture ni de performance n'a été imposé par G0.

## 1. Pourquoi un banc qui n'échoue pas sur les chiffres

Un banc d'essai qui échoue quand les chiffres déplaisent finit par être réglé
pour plaire : on réduit le scénario, on retire l'écriture, on relance jusqu'à
obtenir une bonne série. La baseline décrit alors un système qui n'existe pas,
et personne ne s'en aperçoit parce qu'elle est verte.

Les contrôles portent donc ailleurs — sur ce qui rendrait la mesure
inexploitable :

| Motif d'invalidité | Ce qu'il empêche de croire |
| --- | --- |
| Application non saine avant ou après | Que les chiffres décrivent un système en état de marche |
| Scénario non terminé (aucune réponse en succès) | Qu'un parcours mesuré ait réellement abouti |
| Authentification impossible | Que la charge ait été appliquée sur des routes protégées |
| Données non synthétiques détectées | Que la mesure n'ait pas touché de données réelles |
| Échantillons insuffisants | Qu'un centile sur trois valeurs signifie quelque chose |
| Horloge non monotone | Que les durées soient comparables entre elles |
| Résultat incomplet (p50/p95/p99, débit, provenance) | Que la mesure se rejoue et se compare |
| Environnement non décrit | Que la baseline se compare à quoi que ce soit |
| Interrupteur externe actif (CSA, automate) | Que ce soit le laboratoire, et lui seul, qui ait été mesuré |
| Erreur effacée de l'agrégat, ou réessai déclaré | Que le taux d'erreur publié soit le taux d'erreur observé |

## 2. Stack mesurée

La stack Docker réelle, démarrée depuis `docker-compose.yml` — l'image est
construite dans le job, son identifiant et l'empreinte de son archive sont
enregistrés dans la provenance.

| Service | Rôle dans la mesure |
| --- | --- |
| `proxy` (Caddy) | Terminaison TLS ; la charge entre par où entre un poste du laboratoire |
| `app` | Application mesurée, rôle `web` |
| `scheduler` | Rôle planificateur, présent car il partage la base |
| `analyzer-gateway` | Présent, **interfaces automates désactivées** |
| `postgres` | PostgreSQL 16, base migrée avant la mesure |
| `valkey` | Cache et compteurs |
| `prometheus` | Supervision interne |
| `db-backup` | Sauvegarde périodique, laissée en place : elle existe en exploitation |
| `grafana` | **Non requis, non démarré** — et le job le vérifie |

### Ce que la mesure désactive, et ce que cela coûte

[`scripts/g0_perf_overlay.yml`](../../scripts/g0_perf_overlay.yml) désactive les
deux limiteurs de débit, et rien d'autre :

```yaml
RATE_LIMIT_ENABLED: "false"
LOGIN_RATE_LIMIT_ENABLED: "false"
```

En production, `RATE_LIMIT_REQUESTS=100` par tranche de 60 s et
`LOGIN_RATE_LIMIT_REQUESTS=10` par tranche de 300 s s'appliquent **par adresse
IP**. Un banc d'essai lancé depuis une seule machine partage forcément une seule
adresse : une première exécution l'a confirmé — 77 réponses `429` sur
129 requêtes, et 100 % d'erreurs dès deux utilisateurs simultanés. On ne
mesurait plus le laboratoire, on mesurait le limiteur.

> **Conséquence à retenir, et à instruire au lot D.** Les chiffres publiés ici
> décrivent l'application **sans** ce limiteur. Le limiteur, lui, reste actif en
> exploitation et plafonne le débit soutenu à environ **1,7 requête par seconde
> et par adresse IP** — très en dessous des débits mesurés. Ce n'est pas un
> détail de configuration : tous les postes d'un laboratoire situés derrière un
> même proxy partagent cette adresse. L'état réel des deux réglages est
> enregistré dans `perf-baseline.json`
> (`environment.application_configuration`) : la mesure dit ce qu'elle a
> désactivé, elle ne le dissimule pas.

### Aucun système externe

CSA et interfaces d'automates restent désactivés. Le script ne se contente pas
de lire les variables d'environnement du conteneur : une variable **absente** ne
dit pas « false », elle ne dit rien. Il interroge donc le processus applicatif
lui-même et publie les valeurs effectives dans
`environment.effective_external_switches` :

```
CSA_SYNC_ENABLED = false
ENABLE_DH36_LISTENER = false
ANALYZER_RAW_LISTENER_ENABLED = false
```

Une seule de ces valeurs à `true` invalide la mesure.

## 3. Scénario

Quatorze pas, dans cet ordre, déroulés intégralement à chaque itération de
chaque utilisateur virtuel. Une lecture isolée ne dirait rien d'un laboratoire,
où lire suppose que quelqu'un a écrit juste avant.

| # | Pas | Genre | Route |
| --- | --- | --- | --- |
| 1 | Authentification | lecture | `POST /api/v1/login/access-token` |
| 2 | Création patient | écriture | `POST /api/v1/patients` |
| 3 | Recherche patient | lecture | `GET /api/v1/patients?q=…` |
| 4 | Prescription (NFS + GE) | écriture | `POST /api/v1/exam-orders` |
| 5 | Échantillon (code-barres) | écriture | `POST /api/v1/samples` |
| 6 | Rattachement échantillon | écriture | `POST /api/v1/exam-orders/{id}/collect` |
| 7 | File de travail | lecture | `GET /api/v1/worklist/my` |
| 8 | Consultation d'un ordre | lecture | `GET /api/v1/exam-orders/{id}` |
| 9 | Saisie d'un résultat | écriture | `POST /api/v1/results` |
| 10 | Consultation d'un résultat | lecture | `GET /api/v1/results/{id}` |
| 11 | Libération du compte rendu | écriture | `POST /api/v1/reports/results/{id}/release` |
| 12 | Tableau de bord | lecture | `GET /api/v1/stats/summary` |
| 13 | Facture fictive | écriture | `POST /api/v1/invoices` |
| 14 | Encaissement fictif | écriture | `POST /api/v1/invoices/{id}/payments` |

La facturation passe par un **compte comptable dédié**, créé une fois avant la
mesure : le cloisonnement est réel, un administrateur n'accède pas à la
facturation. Le créer dans la boucle aurait fait passer une création
d'utilisateur pour de la facturation.

Le parcours porte une **empreinte SHA-256** (`run.scenario_sha256`) calculée sur
les noms, genres, méthodes et gabarits d'URL. Changer une route, en retirer un
pas ou en changer l'ordre change cette valeur, et la provenance devient
incohérente avec la mesure — c'est ce qui empêche de republier une baseline
décrivant un parcours qu'on n'exécute plus.

### Données

Strictement synthétiques, et **vérifiées** plutôt que supposées. Tout
identifiant créé porte le préfixe `G0SYNTH-<run_id>-…` ; les noms sont tirés
d'un vocabulaire fermé et manifestement fictif (`Alpha`, `Bravo`, `Charlie`,
`Delta`, `Echo`, `Foxtrot` / `Temoin`, `Fictif`, `Synthetique`, `Essai`, `Banc`,
`Zero`). Un identifiant sans marque ou un nom hors vocabulaire invalide la
mesure. Le contenu est tiré d'un générateur ensemencé (`--seed 20260909`) ;
seuls les identifiants portent un espace de noms propre à l'exécution, faute de
quoi la deuxième exécution violerait les contraintes d'unicité et l'on
prendrait un conflit de clé pour une régression de performance.

### Charge

| Paramètre | Valeur | Pourquoi |
| --- | --- | --- |
| Niveaux de concurrence | **1, 3, 5, 10** | 3 est le premier usage envisagé au CSA GR Plateau : un guichet, un préleveur, un technicien |
| Répétitions par niveau | **3** | En dessous, la dispersion entre exécutions n'est pas observable |
| Chauffe par utilisateur | **2 itérations** | Non mesurées : connexions TLS et caches en cours d'amorçage |
| Itérations mesurées par utilisateur | **5** | Voir la note ci-dessous |
| Réessais | **0** | Un réessai transformerait 8 % d'erreurs en 0 % apparent |
| Centiles | rang le plus proche, sans interpolation | Sur des effectifs modestes, l'interpolation fabrique des valeurs jamais observées |
| Horloge | `time.perf_counter` (monotone) | Vérifiée : aucune durée nulle ou négative, aucun départ antérieur au début de l'exécution |

> **Ce qui est borné pour tenir en CI, et ce qui ne l'est pas.** Le **scénario
> n'est pas réduit** : les quatorze pas, les quatre niveaux et les trois
> répétitions sont exécutés intégralement. Ce qui est borné, c'est le nombre
> d'itérations mesurées par utilisateur virtuel — **5**, après 2 de chauffe.
> Le prix de ce choix est réel et doit être dit : à concurrence 1, un scénario
> donné n'est observé que 15 fois par niveau, et un p99 sur 15 valeurs est le
> quinzième point de la série, pas une queue de distribution. Les centiles
> élevés des niveaux bas sont donc **indicatifs**, et le contrôle d'effectif
> minimum (10 échantillons par scénario et par niveau) est le plancher en
> dessous duquel la mesure est déclarée invalide plutôt que publiée.

## 4. Résultats mesurés

<!-- RESULTATS_PERFORMANCE_DEBUT -->

> **Campagne canonique candidate.** Exécution de CI
> [34786598282 / job 103803102185](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/34786598282/job/103803102185),
> sur la tête `02795a8` (base `981ef35`, arbre `2097ecf`) · identifiant de banc
> `b89ed71dd3` · plan de mesure `4f651fa8f7a8d30b…` · empreinte du scénario
> `84e8e408aff36448…`.
>
> Les six identités sont **embarquées dans `perf-provenance.json`** (champ
> `measurement_identity`). À ne pas confondre avec `baseline_input_commit`,
> qui est l'ancrage historique **déclaré** du programme G0 et non le commit
> mesuré — le document le disait mal, une revue indépendante l'a relevé.
>
> Identités, empreintes des cinq artefacts et identité de l'image :
> [`QUALITY_BASELINE_CANDIDATE_MANIFEST.md`](QUALITY_BASELINE_CANDIDATE_MANIFEST.md).

```
PERFORMANCE_PROFILE = CORE_INTRINSIC_WITH_RATE_LIMITS_DISABLED
```

### 4.1 Environnement de mesure

| | |
| --- | --- |
| Exécuteur | `github-actions/ubuntu-latest` |
| Système | Linux 6.17.0-1022-azure, x86_64 |
| Processeurs | **4** |
| Mémoire | 16 766 414 848 o (≈ 15,6 Gio) |
| Python | 3.13.15 · Docker 28.0.4 |
| PostgreSQL | 16.6 |
| Valkey — **produit** | **8.1.9** |
| Valkey — compatibilité de protocole | `redis_version` 7.2.4 |
| Image Valkey épinglée | `valkey/valkey:8.1.9-alpine@sha256:e0eb7c48…` |
| Image mesurée | `sha256:1edab0d5…` |

> **Deux versions, et les confondre était une erreur de preuve.** `INFO server`
> publie `redis_version:7.2.4` — une compatibilité de **protocole** — et
> `valkey_version:8.1.9` — la version du **produit**. Les campagnes précédentes
> lisaient la première et publiaient « Valkey 7.2.4 », un numéro qui ne désigne
> pas le serveur mesuré. Le champ correct figurait dans la même réponse et était
> ignoré ; le champ générique `version` de l'artefact, qui ne disait pas de quel
> produit il parlait, est ce qui a rendu la confusion invisible.
>
> Relevé par une revue indépendante, pas par les contrôles de cette campagne.
> Ceux-ci refusent désormais un `valkey_version` absent, recopié depuis la
> compatibilité de protocole, ou contredit par le tag de l'image épinglée.

Réglages effectifs lus **dans le processus applicatif**, jamais supposés depuis
l'environnement du runner :

```
PROCESS_ROLE                   = web
CACHE_BACKEND                  = redis
RATE_LIMIT_ENABLED             = false      ← désactivé par la surcharge de mesure
LOGIN_RATE_LIMIT_ENABLED       = false      ← désactivé par la surcharge de mesure
REQUIRE_VALIDATION_FOR_RELEASE = false
CSA_SYNC_ENABLED               = false
ENABLE_DH36_LISTENER           = false
ANALYZER_RAW_LISTENER_ENABLED  = false
```

`effective_external_switches.available = true` : les trois interrupteurs
externes ont été **lus**, pas déduits d'une variable absente. Une variable
absente ne dit pas « false », elle ne dit rien.

### 4.2 Agrégat par niveau de concurrence

| Concurrence | p50 | p95 | p99 | moyenne | max | débit | erreurs |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **1** | 9.341 ms | 14.457 ms | 18.682 ms | 10.208 ms | 166.513 ms | 65.203 req/s | 0/210 |
| **3** | 24.472 ms | 81.365 ms | 111.189 ms | 28.430 ms | 119.579 ms | 72.624 req/s | **6/624** |
| **5** | 43.374 ms | 302.333 ms | 418.212 ms | 64.708 ms | 555.075 ms | 54.189 req/s | **13/1037** |
| **10** | 92.196 ms | 1285.300 ms | 1685.385 ms | 190.262 ms | 1857.323 ms | 37.341 req/s | **45/2058** |

> **Le débit plafonne à trois utilisateurs, puis décroît.** 72,6 req/s à trois,
> 54,2 à cinq, 37,3 à dix : au-delà de trois, ajouter des utilisateurs produit
> moins de travail, pas plus. Le p95 est multiplié par **89** entre un et dix
> utilisateurs.
>
> Ce runner-ci est sensiblement plus rapide que celui de la campagne précédente
> (65 req/s contre 48 à concurrence 1). Les chiffres absolus d'une campagne ne
> se comparent donc pas à ceux d'une autre : c'est la **forme** de la courbe —
> plateau puis décroissance — qui se reproduit d'une campagne à l'autre.

### 4.3 Par scénario — concurrence 3 et 10

Concurrence **3**, le premier usage envisagé au CSA GR Plateau (un guichet, un
préleveur, un technicien) :

| Scénario | Échantillons | p50 | p95 | p99 | max | Erreurs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | 45 | 19.031 | 29.439 | 38.671 | 38.671 | 0 |
| `patient_create` | 45 | 18.987 | 24.706 | 38.300 | 38.300 | 0 |
| `patient_search` | 45 | 13.318 | 16.677 | 19.454 | 19.454 | 0 |
| `order_create` | 45 | 24.043 | 32.388 | 50.383 | 50.383 | 0 |
| `sample_create` | 45 | 24.584 | 31.733 | 37.543 | 37.543 | 0 |
| `sample_attach` | 45 | 34.824 | 42.735 | 58.305 | 58.305 | 0 |
| `worklist` | 45 | 29.251 | 38.437 | 40.040 | 40.040 | 0 |
| `order_read` | 45 | 14.254 | 18.803 | 20.199 | 20.199 | 0 |
| `result_create` | 45 | 32.060 | 40.589 | 45.085 | 45.085 | 0 |
| `result_read` | 45 | 12.042 | 16.176 | 19.402 | 19.402 | 0 |
| `result_release` | 45 | 28.700 | 37.167 | 39.013 | 39.013 | 0 |
| `dashboard` | 45 | **92.227** | **115.266** | **119.579** | 119.579 | 0 |
| `invoice_create` | 45 | 20.872 | 40.491 | 45.656 | 45.656 | **6** (http_500) |
| `payment_create` | **39** | 25.879 | 33.816 | 34.190 | 34.190 | 0 |

Concurrence **10** :

| Scénario | Échantillons | p50 | p95 | p99 | max | Erreurs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | 150 | 66.078 | 119.297 | 227.876 | 232.916 | **3** (http_502) |
| `patient_create` | 150 | 77.328 | 127.962 | 236.290 | 265.326 | 0 |
| `patient_search` | 150 | 50.649 | 76.979 | 89.646 | 94.206 | 0 |
| `order_create` | 150 | 84.631 | 123.896 | 269.159 | 288.602 | 0 |
| `sample_create` | 150 | 99.224 | 132.599 | 293.868 | 305.903 | 0 |
| `sample_attach` | 150 | 119.763 | 169.636 | 314.620 | 332.339 | 0 |
| `worklist` | 150 | 96.189 | 252.721 | 292.437 | 295.699 | 0 |
| `order_read` | 150 | 54.663 | 79.224 | 230.488 | 237.423 | 0 |
| `result_create` | 150 | 121.911 | 157.168 | 326.673 | 331.940 | 0 |
| `result_read` | 150 | 45.728 | 69.980 | 87.955 | 198.140 | 0 |
| `result_release` | 150 | 118.733 | 281.053 | 450.963 | 466.570 | 0 |
| `dashboard` | 150 | **1408.314** | **1790.559** | **1852.006** | 1857.323 | 0 |
| `invoice_create` | 150 | 92.196 | 183.709 | 222.443 | 257.672 | **42** (http_500) |
| `payment_create` | **108** | 99.501 | 222.515 | 301.433 | 311.270 | 0 |

> **`payment_create` n'a que 39 échantillons sur 45 à trois utilisateurs, et
> 108 sur 150 à dix.** Un encaissement suppose une facture émise : les échecs de
> `invoice_create` privent mécaniquement le pas suivant de son objet. Ce n'est
> pas une erreur de mesure, c'est la propagation du défaut dans le parcours — et
> c'est exactement ce qu'un laboratoire observerait.
>
> **`dashboard` est le point lent du système, bien avant la charge** : 92 ms de
> p50 à trois utilisateurs quand aucun autre pas ne dépasse 35 ms, et **1,41 s**
> à dix. La synthèse d'activité est agrégée à chaque appel.

### 4.4 Ressources pendant la charge

> **Ce tableau remplace un tableau qui mesurait le repos.** Les campagnes
> antérieures relevaient `docker stats` **avant** et **après** chaque niveau et
> publiaient le résultat comme s'il décrivait l'effort. Deux instantanés qui
> encadrent une fenêtre ne mesurent pas ce qui s'y passe : le CPU publié pour
> l'application était `0.12 %` à **tous** les niveaux — le chiffre d'une stack
> au repos, et rien dans le fichier ne le disait.
>
> L'échantillonneur relève désormais **en continu pendant la fenêtre de
> charge**. Aucun seuil de CPU ni de mémoire n'est introduit : une consommation
> élevée est un **résultat**. C'est l'absence de mesure qui invalide une
> campagne.

| Conc. | Fenêtre | Échantillons | Par conteneur | Intervalle observé |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3.223 s | 60 | 10 | 0.222 s |
| 3 | 8.596 s | 192 | 32 | 0.242 s |
| 5 | 19.142 s | 444 | 74 | 0.247 s |
| 10 | 55.123 s | 1308 | 218 | 0.249 s |

Tous les échantillons tombent **dans** la fenêtre de charge (`60/60`, `192/192`,
`444/444`, `1308/1308`), l'échantillonneur est vivant à l'arrêt aux quatre
niveaux, et aucune erreur de lecture n'est survenue.

**CPU (% d'un cœur ; la machine en compte 4) :**

| Conc. | `app` moy | `app` p95 | `app` max | `postgres` moy | `postgres` max | `proxy` moy | `valkey` moy |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | **49.4** | 81.5 | 81.5 | 10.1 | 17.6 | 3.0 | 0.13 |
| 3 | **106.7** | 123.9 | 123.9 | 25.6 | 37.0 | 5.4 | 0.48 |
| 5 | **119.3** | 141.9 | 141.9 | 26.5 | 38.1 | 4.4 | 0.42 |
| 10 | **128.0** | 137.1 | 152.7 | 35.9 | 59.9 | 3.2 | 0.37 |

**Mémoire (Mio) :**

| Conc. | `app` moy | `app` max | `postgres` moy | `postgres` max | `proxy` max | `valkey` max |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 137.5 | 137.8 | 36.6 | 36.9 | 22.8 | 13.8 |
| 3 | 143.7 | 145.4 | 46.2 | 47.9 | 23.2 | 13.4 |
| 5 | 148.7 | 150.3 | 54.8 | 59.4 | 27.3 | 13.9 |
| 10 | 165.8 | 174.3 | 68.6 | 75.5 | 29.5 | 13.9 |

> **Ce que cette mesure établit, et que l'ancienne cachait entièrement.**
> L'application consomme déjà **49 % d'un cœur avec un seul utilisateur**, et
> plafonne autour de **1,3 cœur** dès trois. Au-delà, le CPU ne monte presque
> plus (107 → 119 → 128 %) alors que la latence explose et que le débit décroît.
>
> **Ce que cette mesure n'établit pas : la cause.** Une version antérieure de ce
> document concluait « le système n'est pas en attente d'entrées-sorties, il est
> borné par le calcul ». C'était une inférence présentée comme une mesure, et
> une revue indépendante l'a relevée à juste titre. Un plateau de CPU
> **concomitant** à une dégradation des latences est compatible avec plusieurs
> explications, et rien dans cette campagne ne permet de trancher.
>
> Formulation exacte de ce qui est observé : *le profil est compatible avec une
> limitation du chemin applicatif ou du processus web, concomitante à un plateau
> CPU. Les mesures ne permettent pas d'exclure une contention transactionnelle,
> un verrou, une sérialisation, le pool de connexions, le GIL, une file interne,
> ni plusieurs de ces causes combinées.*
>
> Cette campagne apporte d'ailleurs un élément qui va dans le sens de la
> prudence : **sept requêtes SQL dépassent 200 ms**, dont un `COMMIT` à 328 ms.
> La campagne précédente n'en comptait aucune. Un `COMMIT` lent n'est pas du
> calcul applicatif — il est compatible avec une attente de verrou ou de
> journalisation. À lui seul il ne démontre rien non plus ; il suffit à montrer
> qu'une conclusion « c'est le CPU » aurait été prématurée.
>
> ```
> PERFORMANCE_BOTTLENECK_PROFILING_REQUIRED   (P1, investigation)
> ```
>
> Un profilage du processus web sous charge est **requis avant toute mise en
> production sur site**. P1 porte sur l'investigation, pas sur une cause
> démontrée : affirmer que le CPU est la cause unique refermerait la question
> sans l'avoir instruite, et orienterait le lot D vers une piste qui pourrait
> n'être qu'un symptôme.
>
> La mémoire reste modeste et croît lentement (137 → 166 Mio en moyenne). Rien
> n'indique de fuite sur la durée de la campagne — mais quelques minutes ne
> disent rien d'une journée de service.
>
> **Prudence sur les p95 à faible effectif.** À concurrence 1, dix échantillons
> par conteneur : le centile à rang le plus proche y renvoie mécaniquement la
> valeur maximale. Le p95 et le max coïncident donc, et le p95 n'y apporte
> aucune information propre.

### 4.5 PostgreSQL et Valkey

| Conc. | Transactions validées | Annulées | Blocs lus disque | Blocs en cache |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 215 | 255 | 86 | 12 980 |
| 3 | 707 | 800 | 26 | 63 469 |
| 5 | 1 101 | 1 342 | 0 | 152 433 |
| 10 | 2 354 | 2 684 | 0 | 795 385 |

> **Les transactions annulées dépassent les validées à tous les niveaux.** Le
> rapport reste stable (≈ 1,14), ce qui écarte une dérive liée à la charge : il
> s'agit d'un comportement du code, pas d'un symptôme de saturation. Un
> laboratoire n'annule pas plus d'écritures qu'il n'en valide — transmis au
> lot D, non instruit ici.
>
> Les blocs lus depuis le disque tombent à **0** dès cinq utilisateurs : le jeu
> synthétique tient en cache pendant la partie chaude de la campagne. Les
> latences publiées sont donc, très probablement, **exemptes d'attente de
> lecture disque** — ce qui les rend plutôt optimistes par rapport à un site
> dont la base aura grossi.
>
> Ce compteur porte sur les **lectures**. Il ne dit rien des écritures, du
> journal WAL, ni des `fsync` : conclure de ces zéros que la campagne n'a connu
> aucune entrée-sortie irait au-delà de ce qui est mesuré — et le `COMMIT` à
> 328 ms relevé ci-dessous invite précisément à ne pas le conclure.

Valkey en fin de campagne — **serveur 8.1.9**, mode `standalone` : 1002,27 Kio
utilisés, 2 clients connectés, 0 clé, 30 commandes traitées.

**Requêtes lentes journalisées au-delà de 200 ms : 7**, dont un `COMMIT` à
328,652 ms. Aucune requête `SELECT` ou `INSERT` isolée ne domine : la plus
lourde est une insertion de session, et la plus lente est une validation de
transaction. La campagne précédente n'en comptait aucune ; ce compteur varie
donc d'une exécution à l'autre et ne doit pas être lu comme une constante.

### 4.6 Erreurs applicatives observées

| Type | Occurrences | Où |
| --- | ---: | --- |
| `http_500` | **61** | `invoice_create` — 6 à conc. 3, 13 à conc. 5, 42 à conc. 10 |
| `http_502` | **3** | `auth` — à concurrence 10 seulement |

Aucun réessai, aucune erreur exclue de l'agrégat, aucune erreur corrigée ici :
le lot C mesure. Ces constats relèvent du **lot D**.

Validité de la mesure : **valide** — `scripts/g0_perf_baseline.py --validate`
sur le fichier écrit, et `--provenance` sur sa provenance.

<!-- RESULTATS_PERFORMANCE_FIN -->

> **Sur quelle révision ces chiffres portent-ils ?** Sur la tête `02795a8`,
> exactement. Le seul commit postérieur de cette branche est le commit
> **documentaire** qui porte ce paragraphe : il ne touche que des fichiers
> Markdown, donc aucun fichier des ensembles d'entrée `coverage` ou
> `performance`, donc aucune empreinte. Les documents désignent donc légitimement
> `02795a8` comme campagne canonique.

## 5. Erreurs applicatives

Une requête qui échoue est **comptée, classée par type, et publiée**. Elle n'est
ni réessayée, ni exclue de l'agrégat. Le contrôle de validité vérifie en outre
que l'agrégat de chaque niveau porte exactement autant d'erreurs que la somme de
ses scénarios, et que `errors_by_type_total` les totalise : une erreur effacée
entre la mesure et le fichier fait échouer le job.

Les erreurs observées relèvent du **lot D**. Elles ne sont pas corrigées ici :
le lot C mesure, et corriger un défaut découvert en le mesurant reviendrait à
publier la mesure d'un système qu'on vient de changer.

### 5.1 `invoice_create` — échec sous concurrence

```
CSA_SITE_PRODUCTION_GO_BLOCKER
INVOICE_CONCURRENCY_REMEDIATION_REQUIRED
```

**Trois campagnes, trois seuils d'apparition différents.** Le tableau ci-dessous
les met côte à côte parce que publier la seule campagne canonique donnerait une
image fausse de la stabilité du défaut.

| Campagne | conc. 1 | conc. 3 | conc. 5 | conc. 10 |
| --- | ---: | ---: | ---: | ---: |
| `fa45c84` (antérieure au lot B) | 0/15 | 5/45 (11 %) | 13/75 (17 %) | 46/150 (31 %) |
| `9af7c0e` (cette mission) | 0/15 | 6/45 (13 %) | 12/75 (16 %) | 31/150 (21 %) |
| `a74da03` | 0/15 | **0/45** | 11/75 (15 %) | 47/150 (31 %) |
| `6afe098` | 0/15 | 5/45 (11 %) | 9/75 (12 %) | 45/150 (30 %) |
| **`02795a8` (canonique)** | **0/15** | **6/45 (13 %)** | **13/75 (17 %)** | **42/150 (28 %)** |

Ce qui est **établi** par les trois : `invoice_create` est le seul pas du
parcours à échouer, il échoue toujours en `HTTP 500`, jamais à un utilisateur
seul, et son taux croît avec la concurrence. Le profil oriente vers un conflit
d'accès concurrent à l'émission d'une facture — numérotation, verrou ou
transaction.

Ce qui n'est **pas** établi : un palier déterministe. Quatre campagnes sur cinq
montrent des échecs dès trois utilisateurs (11 %, 13 %, 11 %, 13 %) ; une seule
n'en montre aucun à ce niveau, sur un code applicatif identique. Le défaut est
donc **intermittent** — il dépend de l'entrelacement des requêtes.

> **Le classement bloquant est maintenu, et il faut dire pourquoi.** La campagne
> canonique reproduit l'échec à trois utilisateurs, ce qui suffirait. Mais même
> si elle ne l'avait pas reproduit — comme `a74da03` — la conclusion serait la
> même : tirer d'une exécution favorable une garantie que les autres exécutions
> contredisent serait choisir la mesure qui arrange. Un défaut de concurrence
> observé à trois utilisateurs dans quatre campagnes sur cinq est un défaut à
> trois utilisateurs, et **trois utilisateurs simultanés est précisément le
> premier usage envisagé au CSA GR Plateau** (un guichet, un préleveur, un
> technicien).
>
> Dans une facturation clinique, un `500` n'est pas une gêne d'affichage :
> l'acte a-t-il été facturé ou non ? La question se pose pour chaque occurrence,
> et le parcours suivant s'en trouve amputé — `payment_create` n'a recueilli que
> 39 encaissements sur 45 tentatives à trois utilisateurs, et 108 sur 150 à
> dix.

Conservé pour le lot D, sans interprétation ajoutée :

| | Campagne canonique `02795a8` |
| --- | --- |
| Code HTTP | `500` |
| Occurrences / dénominateur | **6/45 à conc. 3** · 13/75 à conc. 5 · 42/150 à conc. 10 · 0/15 à conc. 1 |
| Répétitions concernées | les 3 de chaque niveau |
| Réessais | **aucun** — `run.retries = 0`, contrôlé |

### 5.2 `auth` — `502` à concurrence 10

```
AUTH_CONCURRENCY_INVESTIGATION_REQUIRED   (P2)
```

3 réponses `502` sur 150 à la concurrence 10, et **aucune en dessous**. Un
`502` vient du **proxy**, pas de l'application : la requête n'a pas abouti
jusqu'à elle.

| Campagne | conc. 5 | conc. 10 |
| --- | ---: | ---: |
| `fa45c84` | 0/75 | 6/150 |
| `9af7c0e` | 0/75 | **0/150 — non reproduit** |
| `a74da03` | 0/75 | 7/150 (4,7 %) |
| `6afe098` | **1/75 (1,3 %)** | 5/150 (3,3 %) |
| **`02795a8` (canonique)** | **0/75** | **3/150 (2,0 %)** |

Le constat **se reproduit**, mais il avait disparu d'une campagne sur cinq :
comme `invoice_create`, le phénomène est intermittent. Une seule campagne
(`6afe098`) en a observé une occurrence à **cinq** utilisateurs ; la campagne
canonique n'en observe aucune à ce niveau. Le seuil constaté n'est donc pas
stable non plus.

Il reste classé **P2**. Sur la campagne canonique il n'apparaît qu'à dix
utilisateurs — plus du triple de l'usage envisagé — et coïncide avec un
plateau de CPU (§4.4) : un symptôme de saturation plausible, pas nécessairement
un défaut applicatif propre.

Une réserve doit toutefois accompagner ce classement : la campagne `6afe098` en
a observé une occurrence à **cinq** utilisateurs. Une seule, sur 75 — trop peu
pour conclure, assez pour ne pas écrire « jamais en dessous de dix ». **Le
lot D devra observer ce pas à cinq utilisateurs sur plusieurs campagnes** avant
de trancher ; ni une occurrence isolée ni son absence sur une campagne ne
suffisent.

## 6. Provenance

`artifacts/g0/perf-provenance.json` porte, pour chaque exécution :

- le commit Git mesuré, le runner, l'OS, l'architecture, le nombre de CPU et la
  mémoire ;
- les versions de Docker, Python, PostgreSQL et Valkey — cette dernière
  distinguée de sa compatibilité de protocole Redis ;
- l'identifiant de l'image mesurée et l'empreinte SHA-256 de son archive ;
- la configuration applicative observée et les interrupteurs externes effectifs ;
- le jeu de données, la graine, l'ordre des scénarios et leur empreinte, les
  niveaux de concurrence, les répétitions, la durée et la commande exacte ;
- l'empreinte SHA-256 des fichiers d'entrée (ensemble `performance` :
  le script de mesure, la surcharge, `app/**`, `alembic/**`,
  `docker-compose.yml`, `Dockerfile`, `requirements.txt`).

Le workflow contrôle **schéma, complétude, cohérence et provenance**. Il ne
compare **jamais** des latences octet à octet : elles varient par nature, et un
tel contrôle échouerait à chaque exécution honnête jusqu'à ce que quelqu'un le
désactive.

## 7. Non-vacuité des contrôles

| Mutation appliquée | Refus attendu |
| --- | --- |
| p99 absent d'un scénario, ou d'un agrégat | `sans p99` / `agregat sans p99` |
| Provenance absente ou incomplète | `provenance sans bloc deterministic` |
| Échantillons sous le minimum déclaré | `sous-echantillonne` |
| Moins de trois répétitions | `moins de trois repetitions` |
| Erreur effacée de l'agrégat | `une erreur a ete masquee` |
| Erreur comptée mais non classée | `classification est incomplete` |
| Réessais déclarés | `des reessais ont eu lieu` |
| Identifiant ou nom non synthétique | `identifiant non synthetique` / `hors vocabulaire` |
| Environnement incomplet | `environnement non decrit` |
| Interrupteur externe actif | `systeme externe actif` |
| Scénario modifié sans changement de son empreinte | `l'empreinte du scenario enregistree n'est pas celle du scenario execute` |
| Référence de branche temporaire comme source | `reference temporaire` |

Chaque mutation est accompagnée d'un **témoin** exigeant l'inverse sur la mesure
intacte, dans
[`tests/test_g0_quality_baseline.py`](../../tests/test_g0_quality_baseline.py).
Les charges utiles y sont construites dans le test, jamais relues dans un
artefact produit avant la mutation.

## 8. Limites

1. **Un runner GitHub partagé n'est pas un serveur de laboratoire.** Les chiffres
   valent comme point de comparaison entre révisions mesurées de la même
   manière, pas comme prédiction du comportement au CSA GR Plateau.
2. **Base vide au départ.** Aucun historique n'est chargé : les temps de requête
   sur des tables de quelques milliers de lignes ne préjugent pas de ceux
   observés après des mois d'exploitation.
3. **Un seul poste de charge.** Le client et la stack partagent la même machine ;
   une part du CPU mesurée côté conteneurs est disputée par le banc lui-même.
4. **Le CPU et la mémoire sont désormais mesurés pendant la charge, et cette
   limite a changé de nature.** Elle disait auparavant que `docker stats
   --no-stream` était appelé avant et après chaque niveau, jamais pendant, et
   que les 0,12 % relevés côté application ne devaient surtout pas être lus
   comme la consommation réelle. C'était exact, et c'était un trou dans la
   preuve. Un échantillonneur en flux relève maintenant en continu (§4.4).
   Ce qui subsiste comme limite : l'échantillonnage a lieu **toutes les
   0,25 s environ**, et un pic plus court que cet intervalle peut passer
   entre deux relevés. Les maxima publiés sont donc des minorants des
   pointes réelles, jamais des majorants. À la concurrence 1, quatorze
   échantillons par conteneur suffisent à peine : le p95 y coïncide
   mécaniquement avec le maximum et n'apporte rien de plus.
5. **Plus de transactions annulées que validées.** À la concurrence 10, 2 652
   `xact_rollback` pour 2 326 `xact_commit`. Une partie s'explique par les
   erreurs applicatives observées, une autre par le comportement ordinaire d'une
   session qui se termine sans écriture. Ce banc ne permet pas de trancher entre
   les deux ; le ratio est publié parce qu'il est mesuré, pas parce qu'il est
   interprété.
6. **Limiteurs désactivés** (§2) : le débit publié n'est pas atteignable en
   exploitation depuis une seule adresse IP.
7. **Cinq itérations mesurées par utilisateur** (§3) : les centiles élevés des
   niveaux de faible concurrence reposent sur des effectifs modestes.
8. **Aucune mesure de la restitution navigateur.** Ce banc mesure l'API. Le temps
   perçu par un utilisateur devant l'interface n'est pas ce qui est publié ici.

## 9. Profil intrinsèque et profil opérationnel du site

```
PERFORMANCE_PROFILE            = CORE_INTRINSIC_WITH_RATE_LIMITS_DISABLED
SITE_OPERATIONAL_PROFILE_REQUIRED
```

Cette campagne mesure la **capacité intrinsèque du cœur**, limiteurs de débit
désactivés (§2). C'est un choix assumé et déclaré : avec les limiteurs actifs,
un banc lancé depuis une seule machine mesure le limiteur et non le
laboratoire — une première exécution l'avait confirmé, 77 réponses `429` sur
129 requêtes.

**Elle ne démontre donc rien du comportement du futur site**, et il ne faut pas
lui faire dire ce qu'elle ne dit pas. Le débit de 53 req/s à trois utilisateurs
n'est pas atteignable en exploitation : le limiteur plafonne le débit soutenu à
environ 1,7 requête par seconde et par adresse IP, et tous les postes d'un
laboratoire situés derrière un même proxy partagent cette adresse.

### Ce qu'une campagne de site devra établir, et qui n'est pas établi ici

Une campagne **distincte et obligatoire avant tout pilote réel** devra être
conduite avec :

- les deux limiteurs **actifs** (`RATE_LIMIT_ENABLED`,
  `LOGIN_RATE_LIMIT_ENABLED`) ;
- Caddy en position réelle de terminaison TLS ;
- un `X-Forwarded-For` **réel**, et non l'adresse d'un banc local ;
- `TRUSTED_PROXY_IPS` configuré pour le site — sans quoi le limiteur compte
  toutes les requêtes sur l'adresse du proxy et plafonne le laboratoire entier
  au quota d'un seul poste ;
- **trois clients représentatifs** sur trois adresses distinctes, plutôt qu'un
  banc mono-machine ;
- la protection anti-force-brute active ;
- la vérification qu'aucun `429` ne survient pendant un parcours normal.

> **Cette campagne n'a pas été exécutée.** Aucune phrase de ce document ne doit
> être lue comme si elle l'avait été. Le lot C mesure le cœur ; le
> comportement du site reste à mesurer.
