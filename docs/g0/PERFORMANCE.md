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
> [34776027833 / job 103774175500](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/34776027833/job/103774175500),
> sur la tête `6afe098` (base `981ef35`, arbre `170ca31`) · identifiant de banc
> `4597303edb` · plan de mesure `4f651fa8f7a8d30b…` · empreinte du scénario
> `84e8e408aff36448…`.
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
| PostgreSQL | 16.6 · Valkey 7.2.4 |
| Image mesurée | `sha256:6490d477…` |

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
| **1** | 12.759 ms | 20.098 ms | 26.082 ms | 13.744 ms | 185.553 ms | 48.477 req/s | 0/210 |
| **3** | 33.239 ms | 118.668 ms | 161.427 ms | 39.214 ms | 306.003 ms | 52.923 req/s | **5/625** |
| **5** | 57.037 ms | 405.024 ms | 556.637 ms | 84.787 ms | 652.640 ms | 41.040 req/s | **10/1041** |
| **10** | 122.733 ms | 1547.293 ms | 2247.785 ms | 251.481 ms | 2541.438 ms | 28.286 req/s | **50/2055** |

> **Le débit plafonne à trois utilisateurs, puis décroît.** 52,9 req/s à trois,
> 41,0 à cinq, 28,3 à dix : ajouter des utilisateurs au-delà de trois ne produit
> plus de travail supplémentaire, il en produit moins. Le p95 est multiplié par
> **77** entre un et dix utilisateurs. La section 4.4 dit pourquoi.

### 4.3 Par scénario — concurrence 3 et 10

Concurrence **3**, le premier usage envisagé au CSA GR Plateau (un guichet, un
préleveur, un technicien) :

| Scénario | Échantillons | p50 | p95 | p99 | max | Erreurs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | 45 | 26.272 | 35.894 | 43.640 | 43.640 | 0 |
| `patient_create` | 45 | 26.825 | 34.174 | 57.147 | 57.147 | 0 |
| `patient_search` | 45 | 18.498 | 26.004 | 26.195 | 26.195 | 0 |
| `order_create` | 45 | 32.473 | 39.675 | 42.072 | 42.072 | 0 |
| `sample_create` | 45 | 33.910 | 38.159 | 40.482 | 40.482 | 0 |
| `sample_attach` | 45 | 43.310 | 54.575 | 55.132 | 55.132 | 0 |
| `worklist` | 45 | 40.017 | 48.021 | 53.184 | 53.184 | 0 |
| `order_read` | 45 | 20.348 | 25.910 | 27.898 | 27.898 | 0 |
| `result_create` | 45 | 42.760 | 50.928 | 51.355 | 51.355 | 0 |
| `result_read` | 45 | 16.441 | 24.140 | 25.090 | 25.090 | 0 |
| `result_release` | 45 | 40.270 | 49.762 | 51.700 | 51.700 | 0 |
| `dashboard` | 45 | **128.296** | **172.437** | **306.003** | 306.003 | 0 |
| `invoice_create` | 45 | 28.719 | 50.410 | 55.050 | 55.050 | **5** (http_500) |
| `payment_create` | **40** | 33.717 | 65.610 | 183.487 | 183.487 | 0 |

Concurrence **10** :

| Scénario | Échantillons | p50 | p95 | p99 | max | Erreurs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | 150 | 86.523 | 169.872 | 270.503 | 281.333 | **5** (http_502) |
| `patient_create` | 150 | 106.718 | 194.714 | 270.233 | 271.429 | 0 |
| `patient_search` | 150 | 73.528 | 120.374 | 219.079 | 247.494 | 0 |
| `order_create` | 150 | 117.592 | 170.186 | 263.592 | 267.260 | 0 |
| `sample_create` | 150 | 135.516 | 193.005 | 308.649 | 323.526 | 0 |
| `sample_attach` | 150 | 163.818 | 221.465 | 313.510 | 333.792 | 0 |
| `worklist` | 150 | 125.489 | 177.352 | 282.958 | 284.895 | 0 |
| `order_read` | 150 | 71.784 | 117.740 | 217.454 | 243.286 | 0 |
| `result_create` | 150 | 164.739 | 224.653 | 320.794 | 331.257 | 0 |
| `result_read` | 150 | 60.868 | 91.780 | 134.738 | 238.676 | 0 |
| `result_release` | 150 | 160.907 | 218.521 | 254.931 | 289.885 | 0 |
| `dashboard` | 150 | **1970.297** | **2354.884** | **2502.442** | 2541.438 | 0 |
| `invoice_create` | 150 | 123.067 | 190.569 | 210.503 | 376.116 | **45** (http_500) |
| `payment_create` | **105** | 127.397 | 224.003 | 336.704 | 338.095 | 0 |

> **`payment_create` n'a que 40 échantillons sur 45 à trois utilisateurs, et 105
> sur 150 à dix.** Un encaissement ne peut avoir lieu que si la facture qui le
> précède a été émise : les échecs de `invoice_create` privent mécaniquement le
> pas suivant de son objet. Ce n'est pas une erreur de mesure, c'est la
> propagation du défaut dans le parcours — et c'est exactement ce qu'un
> laboratoire observerait.
>
> **`dashboard` est le point lent du système, bien avant la charge** : 128 ms de
> p50 à trois utilisateurs quand aucun autre pas ne dépasse 44 ms, et **1,97 s**
> à dix. La synthèse d'activité est agrégée à chaque appel.

### 4.4 Ressources pendant la charge

> **Ce tableau remplace un tableau qui mesurait le repos.** Les campagnes
> précédentes relevaient `docker stats` **avant** et **après** chaque niveau et
> publiaient le résultat comme s'il décrivait l'effort. Deux instantanés qui
> encadrent une fenêtre ne mesurent pas ce qui s'y passe. Le CPU publié pour
> l'application était `0.12 %` à **tous** les niveaux de concurrence — le
> chiffre d'une stack au repos, et rien dans le fichier ne le disait.
>
> L'échantillonneur relève désormais **en continu pendant la fenêtre de
> charge**. Aucun seuil de CPU ni de mémoire n'est introduit : une consommation
> élevée est un **résultat**. C'est l'absence de mesure qui invalide une
> campagne.

| Conc. | Fenêtre | Échantillons | Par conteneur | Intervalle observé |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 4.334 s | 96 | 16 | 0.233 s |
| 3 | 11.814 s | 276 | 46 | 0.244 s |
| 5 | 25.372 s | 600 | 100 | 0.247 s |
| 10 | 72.664 s | 1728 | 288 | 0.249 s |

Tous les échantillons tombent **dans** la fenêtre de charge (`96/96`, `276/276`,
`600/600`, `1728/1728`), l'échantillonneur est vivant à l'arrêt aux quatre
niveaux, et aucune erreur de lecture n'est survenue.

**CPU (% d'un cœur ; la machine en compte 4) :**

| Conc. | `app` moy | `app` p95 | `app` max | `postgres` moy | `postgres` max | `proxy` moy | `valkey` moy |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | **63.0** | 84.5 | 84.5 | 12.4 | 17.1 | 4.4 | 0.12 |
| 3 | **114.3** | 128.3 | 128.6 | 24.8 | 38.9 | 5.6 | 0.43 |
| 5 | **123.7** | 132.7 | 132.8 | 27.8 | 36.9 | 4.6 | 0.39 |
| 10 | **130.5** | 139.6 | 160.1 | 34.7 | 57.3 | 3.3 | 0.47 |

**Mémoire (Mio) :**

| Conc. | `app` moy | `app` max | `postgres` moy | `postgres` max | `proxy` max | `valkey` max |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 137.2 | 137.8 | 36.3 | 36.8 | 23.9 | 13.4 |
| 3 | 143.0 | 145.6 | 46.9 | 47.9 | 26.0 | 13.9 |
| 5 | 149.0 | 151.2 | 55.7 | 59.2 | 30.3 | 20.6 |
| 10 | 166.7 | 183.7 | 69.7 | 75.9 | 30.9 | 13.9 |

> **Ce que cette mesure établit, et que l'ancienne cachait entièrement.**
> L'application consomme déjà **63 % d'un cœur avec un seul utilisateur**, et
> sature autour de **1,3 cœur** dès trois. Au-delà, le CPU ne monte presque plus
> (114 → 124 → 130 %) alors que la latence explose : le système n'est pas en
> attente d'entrées-sorties, il est **borné par le calcul**. C'est cohérent avec
> un débit qui plafonne à trois utilisateurs puis décroît.
>
> La mémoire reste modeste et croît lentement (137 → 167 Mio en moyenne). Rien
> n'indique de fuite sur la durée de la campagne — mais une campagne de quelques
> minutes ne dit rien d'une journée de service.
>
> **Prudence sur les p95 à faible effectif.** À concurrence 1, seize
> échantillons par conteneur : le centile à rang le plus proche y renvoie
> mécaniquement la valeur maximale. Le p95 et le max coïncident donc, et le p95
> n'y apporte aucune information propre.

### 4.5 PostgreSQL et Valkey

| Conc. | Transactions validées | Annulées | Blocs lus disque | Blocs en cache |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 199 | 237 | 86 | 12 172 |
| 3 | 732 | 839 | 26 | 64 552 |
| 5 | 1 121 | 1 350 | 0 | 147 784 |
| 10 | 2 339 | 2 653 | 1 | 741 195 |

> **Les transactions annulées dépassent les validées à tous les niveaux.** Le
> rapport reste stable (≈ 1,15), ce qui écarte une dérive liée à la charge : il
> s'agit d'un comportement du code, pas d'un symptôme de saturation. Un
> laboratoire n'annule pas plus d'écritures qu'il n'en valide — ce point est
> transmis au lot D, non instruit ici.
>
> Les blocs lus depuis le disque tombent à **0** dès cinq utilisateurs : le jeu
> synthétique tient intégralement en cache. Les latences publiées ne contiennent
> donc **aucune attente de disque**, ce qui les rend plutôt optimistes par
> rapport à un site dont la base aura grossi.

Valkey en fin de campagne : 1002,02 Kio utilisés, 2 clients connectés, 0 clé,
33 commandes traitées. **Requêtes lentes journalisées au-delà de 200 ms : 0** —
le temps ne se perd pas dans les requêtes SQL.

### 4.6 Erreurs applicatives observées

| Type | Occurrences | Où |
| --- | ---: | --- |
| `http_500` | **59** | `invoice_create` — 5 à conc. 3, 9 à conc. 5, 45 à conc. 10 |
| `http_502` | **6** | `auth` — 1 à conc. 5, 5 à conc. 10 |

Aucun réessai, aucune erreur exclue de l'agrégat, aucune erreur corrigée ici :
le lot C mesure. Ces constats relèvent du **lot D**.

Validité de la mesure : **valide** — `scripts/g0_perf_baseline.py --validate`
sur le fichier écrit, et `--provenance` sur sa provenance.

<!-- RESULTATS_PERFORMANCE_FIN -->

> **Sur quelle révision ces chiffres portent-ils ?** Sur la tête `6afe098`,
> exactement. Le seul commit postérieur de cette branche est le commit
> **documentaire** qui porte ce paragraphe : il ne touche que des fichiers
> Markdown, donc aucun fichier des ensembles d'entrée `coverage` ou
> `performance`, donc aucune empreinte. Les documents désignent donc légitimement
> `6afe098` comme campagne canonique.

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
| `a74da03` (cette mission) | 0/15 | **0/45** | 11/75 (15 %) | 47/150 (31 %) |
| **`6afe098` (canonique)** | **0/15** | **5/45 (11 %)** | **9/75 (12 %)** | **45/150 (30 %)** |

Ce qui est **établi** par les trois : `invoice_create` est le seul pas du
parcours à échouer, il échoue toujours en `HTTP 500`, jamais à un utilisateur
seul, et son taux croît avec la concurrence. Le profil oriente vers un conflit
d'accès concurrent à l'émission d'une facture — numérotation, verrou ou
transaction.

Ce qui n'est **pas** établi : un palier déterministe. Trois campagnes sur quatre
montrent des échecs dès trois utilisateurs (11 %, 13 %, 11 %) ; la quatrième
n'en montre aucun à ce niveau, sur un code applicatif identique. Le défaut est
donc **intermittent** — il dépend de l'entrelacement des requêtes.

> **Le classement bloquant est maintenu, et il faut dire pourquoi.** La campagne
> canonique reproduit l'échec à trois utilisateurs, ce qui suffirait. Mais même
> si elle ne l'avait pas reproduit — comme `a74da03` — la conclusion serait la
> même : tirer d'une exécution favorable une garantie que les autres exécutions
> contredisent serait choisir la mesure qui arrange. Un défaut de concurrence
> observé à trois utilisateurs dans trois campagnes sur quatre est un défaut à
> trois utilisateurs, et **trois utilisateurs simultanés est précisément le
> premier usage envisagé au CSA GR Plateau** (un guichet, un préleveur, un
> technicien).
>
> Dans une facturation clinique, un `500` n'est pas une gêne d'affichage :
> l'acte a-t-il été facturé ou non ? La question se pose pour chaque occurrence,
> et le parcours suivant s'en trouve amputé — `payment_create` n'a recueilli que
> 40 encaissements sur 45 tentatives à trois utilisateurs, et 105 sur 150 à
> dix.

Conservé pour le lot D, sans interprétation ajoutée :

| | Campagne canonique `6afe098` |
| --- | --- |
| Code HTTP | `500` |
| Occurrences / dénominateur | **5/45 à conc. 3** · 9/75 à conc. 5 · 45/150 à conc. 10 · 0/15 à conc. 1 |
| Répétitions concernées | les 3 de chaque niveau |
| Réessais | **aucun** — `run.retries = 0`, contrôlé |

### 5.2 `auth` — `502` à concurrence 10

```
AUTH_CONCURRENCY_INVESTIGATION_REQUIRED   (P2)
```

5 réponses `502` sur 150 à la concurrence 10, et **1 sur 75 à la concurrence
5** — un niveau où il n'avait jamais été observé jusqu'ici. Un `502` vient du
**proxy**, pas de l'application : la requête n'a pas abouti jusqu'à elle.

| Campagne | conc. 5 | conc. 10 |
| --- | ---: | ---: |
| `fa45c84` | 0/75 | 6/150 |
| `9af7c0e` | 0/75 | **0/150 — non reproduit** |
| `a74da03` | 0/75 | 7/150 (4,7 %) |
| **`6afe098` (canonique)** | **1/75 (1,3 %)** | **5/150 (3,3 %)** |

Le constat **se reproduit**, mais il avait disparu d'une campagne sur quatre :
comme `invoice_create`, le phénomène est intermittent. La campagne canonique en
observe en outre une occurrence à cinq utilisateurs, ce qui abaisse le seuil
constaté par rapport aux campagnes précédentes.

Il reste classé **P2**, et la mesure ne justifie pas de le monter — mais la
justification a changé, et il faut le dire. Elle reposait sur « il n'apparaît
qu'à dix utilisateurs, plus du triple de l'usage envisagé ». La campagne
canonique en montre **une occurrence à cinq**, donc cet argument ne tient plus
seul. Ce qui le maintient en P2 : une occurrence unique sur 75 à ce niveau, et
la coïncidence avec un système déjà saturé en CPU (§4.4) — un symptôme de
saturation plausible, pas nécessairement un défaut applicatif propre.

Le monter en P1 sur un échantillon de 1/75 serait une conclusion sans mesure,
au même titre que le descendre. **Le lot D devra observer ce pas à cinq
utilisateurs sur plusieurs campagnes** avant de trancher ; une occurrence isolée
ne suffit ni à confirmer ni à écarter.

## 6. Provenance

`artifacts/g0/perf-provenance.json` porte, pour chaque exécution :

- le commit Git mesuré, le runner, l'OS, l'architecture, le nombre de CPU et la
  mémoire ;
- les versions de Docker, Python, PostgreSQL et Valkey ;
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
