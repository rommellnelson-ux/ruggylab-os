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

> Exécution de CI : [34363173460 / job 102505089035](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/34363173460/job/102505089035), commit `fa45c84`
> · commit mesuré `c5a788e36283` · image `sha256:45eb5f3c627b…` · archive `21a68afbf9acd8a5…`

### 4.1 Environnement de mesure

| | |
| --- | --- |
| Runner | github-actions/ubuntu-latest |
| OS / architecture | Linux 6.17.0-1022-azure — x86_64 |
| CPU | 4 cœurs logiques |
| Mémoire | 16.8 Go totale, 15.1 Go disponible au démarrage |
| Docker | 28.0.4 |
| Python (banc) | 3.13.15 |
| PostgreSQL | PostgreSQL 16.6 |
| Valkey (version annoncée par `INFO`) | 7.2.4 |
| Graine | `20260909` |
| Durée totale | 134.758 s |
| Empreinte du scénario | `84e8e408aff36448…` |
| Empreinte des entrées | `77f0c21e7b3e1f7d…` sur 295 fichiers |
| Appels réseau externes | aucun |

Commande exacte :

```bash
python scripts/g0_perf_baseline.py --run --base-url https://localhost --concurrency 1,3,5,10 --repetitions 3 --iterations 5 --warmup 2 --seed 20260909
```

Interrupteurs externes effectifs, lus dans le processus applicatif :

- `ANALYZER_RAW_LISTENER_ENABLED` = `false`
- `CSA_SYNC_ENABLED` = `false`
- `ENABLE_DH36_LISTENER` = `false`

Configuration applicative observée :

- `ANALYZER_RAW_LISTENER_ENABLED` = *non transmise au conteneur*
- `CACHE_BACKEND` = `redis`
- `CSA_SYNC_ENABLED` = *non transmise au conteneur*
- `ENABLE_DH36_LISTENER` = *non transmise au conteneur*
- `LOGIN_RATE_LIMIT_ENABLED` = `false`
- `PROCESS_ROLE` = `web`
- `RATE_LIMIT_ENABLED` = `false`
- `REQUIRE_VALIDATION_FOR_RELEASE` = `false`
- `TRUSTED_PROXY_IPS` = `["172.28.117.10"]`

### 4.2 Agrégat par niveau de concurrence

> Les latences n'agrègent que les réponses en succès. Mêler la latence d'un 500 immédiat à celle d'une réponse utile ferait baisser les centiles à mesure que le système se dégrade — l'inverse de ce qu'on veut lire. Le taux d'erreur est publié à côté, jamais fondu dedans.

| Concurrence | Échantillons | p50 ms | p95 ms | p99 ms | moyenne ms | max ms | débit req/s | erreurs | taux |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **1** | 210 | **11.7** | **18.8** | **24.2** | 12.0 | 141.6 | **55.35** | 0 | 0.00 % |
| **10** | 2054 | **120.0** | **1603.3** | **2180.0** | 242.3 | 2522.2 | **29.359** | 52 | 2.53 % |
| **3** | 625 | **30.3** | **97.1** | **142.2** | 35.5 | 163.6 | **58.208** | 5 | 0.80 % |
| **5** | 1037 | **55.0** | **363.3** | **515.3** | 80.9 | 543.6 | **43.679** | 13 | 1.25 % |

### 4.3 Par scénario et par niveau

#### Concurrence 1

| Scénario | Genre | Échantillons | p50 ms | p95 ms | p99 ms | max ms | erreurs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | read | 15 | 12.4 | 12.9 | 12.9 | 12.9 | 0 |
| `patient_create` | write | 15 | 8.8 | 9.1 | 9.1 | 9.1 | 0 |
| `patient_search` | read | 15 | 6.7 | 7.0 | 7.0 | 7.0 | 0 |
| `order_create` | write | 15 | 10.8 | 12.5 | 12.5 | 12.5 | 0 |
| `sample_create` | write | 15 | 10.2 | 11.0 | 11.0 | 11.0 | 0 |
| `sample_attach` | write | 15 | 14.2 | 16.3 | 16.3 | 16.3 | 0 |
| `worklist` | read | 15 | 13.5 | 23.0 | 23.0 | 23.0 | 0 |
| `order_read` | read | 15 | 6.8 | 7.4 | 7.4 | 7.4 | 0 |
| `result_create` | write | 15 | 13.5 | 14.4 | 14.4 | 14.4 | 0 |
| `result_read` | read | 15 | 6.0 | 6.1 | 6.1 | 6.1 | 0 |
| `result_release` | write | 15 | 13.4 | 15.3 | 15.3 | 15.3 | 0 |
| `dashboard` | read | 15 | 19.9 | 141.6 | 141.6 | 141.6 | 0 |
| `invoice_create` | write | 15 | 10.6 | 11.7 | 11.7 | 11.7 | 0 |
| `payment_create` | write | 15 | 12.9 | 13.4 | 13.4 | 13.4 | 0 |

#### Concurrence 10

| Scénario | Genre | Échantillons | p50 ms | p95 ms | p99 ms | max ms | erreurs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | read | 150 | 81.8 | 190.4 | 308.9 | 329.8 | **6** (http_502×6) |
| `patient_create` | write | 150 | 99.8 | 175.0 | 301.8 | 350.0 | 0 |
| `patient_search` | read | 150 | 67.6 | 103.5 | 216.5 | 220.1 | 0 |
| `order_create` | write | 150 | 116.3 | 160.9 | 242.2 | 249.0 | 0 |
| `sample_create` | write | 150 | 127.4 | 189.2 | 303.8 | 327.1 | 0 |
| `sample_attach` | write | 150 | 154.6 | 302.1 | 364.1 | 381.0 | 0 |
| `worklist` | read | 150 | 127.2 | 281.4 | 298.4 | 338.7 | 0 |
| `order_read` | read | 150 | 70.0 | 106.8 | 257.0 | 289.8 | 0 |
| `result_create` | write | 150 | 158.8 | 329.8 | 365.4 | 366.0 | 0 |
| `result_read` | read | 150 | 60.2 | 91.7 | 209.1 | 247.3 | 0 |
| `result_release` | write | 150 | 152.8 | 206.5 | 331.2 | 333.9 | 0 |
| `dashboard` | read | 150 | 1723.2 | 2326.8 | 2474.2 | 2522.2 | 0 |
| `invoice_create` | write | 150 | 114.5 | 176.5 | 234.7 | 264.3 | **46** (http_500×46) |
| `payment_create` | write | 104 | 130.1 | 185.6 | 201.9 | 247.1 | 0 |

#### Concurrence 3

| Scénario | Genre | Échantillons | p50 ms | p95 ms | p99 ms | max ms | erreurs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | read | 45 | 23.6 | 40.9 | 50.4 | 50.4 | 0 |
| `patient_create` | write | 45 | 24.7 | 38.3 | 39.6 | 39.6 | 0 |
| `patient_search` | read | 45 | 17.6 | 21.2 | 24.2 | 24.2 | 0 |
| `order_create` | write | 45 | 29.3 | 36.4 | 39.3 | 39.3 | 0 |
| `sample_create` | write | 45 | 30.3 | 39.2 | 40.0 | 40.0 | 0 |
| `sample_attach` | write | 45 | 41.2 | 50.0 | 59.0 | 59.0 | 0 |
| `worklist` | read | 45 | 35.8 | 43.9 | 48.8 | 48.8 | 0 |
| `order_read` | read | 45 | 17.9 | 24.2 | 26.4 | 26.4 | 0 |
| `result_create` | write | 45 | 40.6 | 48.0 | 52.4 | 52.4 | 0 |
| `result_read` | read | 45 | 14.5 | 22.0 | 24.1 | 24.1 | 0 |
| `result_release` | write | 45 | 37.4 | 45.3 | 50.9 | 50.9 | 0 |
| `dashboard` | read | 45 | 118.9 | 150.2 | 163.6 | 163.6 | 0 |
| `invoice_create` | write | 45 | 27.3 | 42.6 | 56.3 | 56.3 | **5** (http_500×5) |
| `payment_create` | write | 40 | 33.1 | 47.6 | 53.1 | 53.1 | 0 |

#### Concurrence 5

| Scénario | Genre | Échantillons | p50 ms | p95 ms | p99 ms | max ms | erreurs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth` | read | 75 | 41.3 | 56.4 | 76.6 | 76.6 | 0 |
| `patient_create` | write | 75 | 45.8 | 64.3 | 193.8 | 193.8 | 0 |
| `patient_search` | read | 75 | 29.1 | 44.8 | 166.2 | 166.2 | 0 |
| `order_create` | write | 75 | 54.5 | 67.2 | 199.4 | 199.4 | 0 |
| `sample_create` | write | 75 | 57.3 | 81.8 | 224.1 | 224.1 | 0 |
| `sample_attach` | write | 75 | 73.1 | 94.5 | 243.2 | 243.2 | 0 |
| `worklist` | read | 75 | 64.6 | 86.0 | 224.4 | 224.4 | 0 |
| `order_read` | read | 75 | 32.6 | 51.3 | 196.2 | 196.2 | 0 |
| `result_create` | write | 75 | 72.7 | 99.4 | 109.5 | 109.5 | 0 |
| `result_read` | read | 75 | 28.0 | 42.3 | 60.0 | 60.0 | 0 |
| `result_release` | write | 75 | 69.6 | 87.1 | 102.8 | 102.8 | 0 |
| `dashboard` | read | 75 | 419.1 | 537.3 | 543.6 | 543.6 | 0 |
| `invoice_create` | write | 75 | 47.1 | 86.2 | 97.8 | 97.8 | **13** (http_500×13) |
| `payment_create` | write | 62 | 60.7 | 83.2 | 92.8 | 92.8 | 0 |

### 4.4 Ressources observées

| Concurrence | CPU app | Mémoire app | CPU PostgreSQL | Mémoire PostgreSQL | Connexions PG | Transactions validées | Transactions annulées |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| **1** | 0.12% | 138.3MiB / 1GiB | 2.84% | 36.43MiB / 1GiB | 2 | 183 | 219 |
| **10** | 0.12% | 172.3MiB / 1GiB | 0.01% | 54.35MiB / 1GiB | 6 | 2326 | 2652 |
| **3** | 0.12% | 145.7MiB / 1GiB | 0.03% | 47.35MiB / 1GiB | 5 | 736 | 833 |
| **5** | 0.12% | 151.6MiB / 1GiB | 0.03% | 53.66MiB / 1GiB | 6 | 1123 | 1369 |

Valkey en fin de mesure : 1002.52K utilisés, 2 clients connectés, 0 bloqués, 0 clés, 20 commandes traitées.

Requêtes lentes journalisées au-delà de 200 ms : **7**.

### 4.5 Erreurs applicatives observées

| Type | Occurrences |
| --- | ---: |
| `http_500` | **64** |
| `http_502` | **6** |

Ces erreurs ne sont ni réessayées, ni exclues de l'agrégat, ni corrigées ici : le lot C mesure. Elles relèvent du **lot D**.

Validité de la mesure : **valide** (scripts/g0_perf_baseline.py valider()).

<!-- RESULTATS_PERFORMANCE_FIN -->

## 5. Erreurs applicatives

Une requête qui échoue est **comptée, classée par type, et publiée**. Elle n'est
ni réessayée, ni exclue de l'agrégat. Le contrôle de validité vérifie en outre
que l'agrégat de chaque niveau porte exactement autant d'erreurs que la somme de
ses scénarios, et que `errors_by_type_total` les totalise : une erreur effacée
entre la mesure et le fichier fait échouer le job.

Les erreurs observées relèvent du **lot D**. Elles ne sont pas corrigées ici :
le lot C mesure, et corriger un défaut découvert en le mesurant reviendrait à
publier la mesure d'un système qu'on vient de changer.

### Ce que l'exécution de référence a observé

Deux défauts distincts, et ils ne se répartissent pas au hasard :

1. **`invoice_create` répond `500` sous concurrence, et de plus en plus
   souvent.** Aucune erreur à un utilisateur ; 5 sur 45 (11 %) à trois ;
   13 sur 75 (17 %) à cinq ; 46 sur 150 (31 %) à dix. Le taux croît avec la
   concurrence sur ce seul pas d'écriture, ce qui oriente vers un conflit
   d'accès concurrent à l'émission d'une facture — numérotation, verrou ou
   transaction. **Trois utilisateurs simultanés est le premier usage envisagé
   au CSA GR Plateau** : ce n'est pas un défaut de charge extrême. À instruire
   en priorité au lot D.
2. **`auth` répond `502` six fois sur 150 au seul niveau 10.** Un `502` vient
   du proxy, pas de l'application : la requête n'a pas abouti jusqu'à elle.
   C'est un symptôme de saturation, pas nécessairement un défaut applicatif.

Aucune de ces erreurs n'a été réessayée, exclue, ni corrigée. Elles sont dans
l'agrégat, dans le détail par scénario, et dans `errors_by_type_total`.

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
4. **Les chiffres de CPU et de mémoire sont des instantanés, pas des pointes.**
   `docker stats --no-stream` est appelé **avant** et **après** chaque niveau,
   jamais pendant. Les valeurs publiées décrivent donc l'état de la stack au
   repos, immédiatement après la charge — la consommation de CPU **au pic** n'a
   pas été mesurée, et les 0,12 % relevés côté application ne doivent surtout
   pas être lus comme « l'application a consommé 0,12 % de CPU pendant la
   mesure ». Ce qui reste exploitable dans ces relevés est ce qui ne redescend
   pas : la mémoire résidente (138 → 172 Mio de la concurrence 1 à 10), le
   nombre de connexions PostgreSQL, et les compteurs de transactions, qui sont
   cumulés et donc pris en différence. Mesurer les pointes demanderait un
   échantillonnage périodique pendant la charge ; c'est une amélioration à
   instruire, pas un résultat de cette campagne.
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
