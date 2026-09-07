# G0 — Inventaire architecture, runtime et données

> **Généré, jamais recopié.** Tous les chiffres viennent de
> [`scripts/g0_inventory.py`](../../scripts/g0_inventory.py) et de
> [`scripts/g0_schema_inventory.py`](../../scripts/g0_schema_inventory.py).
> La CI régénère et compare : un inventaire qui dérive fait échouer le job.
>
> Provenance : [`artifacts/g0/provenance.json`](../../artifacts/g0/provenance.json)

## 1. Chiffres préliminaires contre chiffres générés

Le plan G0 avait relevé des nombres avant tout inventaire outillé. **Ils
n'étaient pas des cibles** — voici la confrontation.

| Mesure | Préliminaire | **Généré** | Écart |
| --- | --- | --- | --- |
| Modules Python (`app/`) | 230 | **230** | — |
| Lignes (`app/`) | ~32 400 | **32 406** | — |
| Chemins OpenAPI | 198 | **198** | — |
| Opérations OpenAPI | 231 | **231** | — |
| Tables PostgreSQL | 49 | **49** | — |
| Migrations Alembic | 43 | **43** | — |
| Rôles applicatifs | 4 | **4** | — |
| Modules à appels sortants | 14 | **voir §6** | à requalifier |

Les sept premiers concordent. **Le huitième ne veut rien dire tel quel** : le
chiffre de 14 provenait d'un `grep` sur `httpx|requests|urllib`, qui compte les
modules *important* une bibliothèque HTTP — pas les frontières externes
réelles. Il est requalifié au §6.

> **Ce que la concordance prouve, et ce qu'elle ne prouve pas.** Elle confirme
> que les comptages approximatifs étaient justes. Elle ne dit rien de ce que
> ces nombres *contiennent* — et c'est là que l'inventaire outillé apporte
> vraiment quelque chose : les **8 routes hors OpenAPI** et les **6 routes non
> authentifiées** du §4 n'apparaissaient dans aucun comptage préalable.

## 2. Application

| | |
| --- | --- |
| Modules Python | **230** |
| Lignes | **32 406** |
| Paquets | voir `inventory.json` → `application.packages` |
| Scripts CLI | **23** |

### Processus

| Processus | Commande | Rôle | État par défaut |
| --- | --- | --- | --- |
| `web` | `uvicorn app.main:app` | API, interface, WebSocket | activé |
| `scheduler` | `python -m app.scheduler` | tâches périodiques, purge des jetons | activé |
| `analyzer-gateway` | `python -m app.analyzer_gateway` | hôte des interfaces d'équipement | activé, **toutes interfaces désactivées** |
| `migrate` | `alembic upgrade head` | migrations | manuel (profil `migrate`) |

### Réglages de gouvernance — état par défaut constaté

| Réglage | Défaut |
| --- | --- |
| `CSA_SYNC_ENABLED` | `False` |
| `ENABLE_DH36_LISTENER` | `False` |
| `ANALYZER_RAW_LISTENER_ENABLED` | `False` |
| `ANALYZER_BIND_IP` | `"127.0.0.1"` |
| `CACHE_BACKEND` | `"memory"` |
| `REQUIRE_VALIDATION_FOR_RELEASE` | `False` |

> **Le dernier est un constat, pas une approbation.** `REQUIRE_VALIDATION_FOR_RELEASE=False`
> signifie qu'un résultat peut être libéré sans validation biologique. C'est
> une limite déjà consignée au CHANGELOG ; l'inventaire la confirme et la
> transmet au backlog du lot D.

## 3. Docker Compose — cinq fichiers, trois statuts

| Fichier | Statut | Services | Rôle |
| --- | --- | --- | --- |
| `docker-compose.yml` | **`core`** | 9 | stack de production, mode nominal supporté |
| `docker-compose.dev.yml` | `dev_override` | 7 | surcharge de développement |
| `docker-compose.monitoring.yml` | `optional_overlay` | 1 | Grafana, **hors du cœur** |
| `docker-compose.monitoring.dev.yml` | `dev_override` | 1 | port loopback pour l'overlay |
| `docker-compose.analyzers.yml` | `optional_overlay` | 1 | interfaces automates, **désactivées** |

### Services du cœur

```
analyzer-gateway · app · db-backup · migrate · postgres · prometheus · proxy · scheduler · valkey
```

**Neuf services.** Variables obligatoires pour les démarrer : `SECRET_KEY`,
`POSTGRES_PASSWORD`, `FIRST_SUPERUSER_PASSWORD`, `RUGGYLAB_IMAGE`. **Aucune
variable Grafana.**

### Deux vérifications explicites

| Contrôle | Résultat |
| --- | --- |
| Grafana classé dans le cœur ? | **non** — `optional_overlay` uniquement |
| Serveur Redis 7.4 actif ? | **non** — remplacé par `valkey/valkey:8.1.9-alpine`, épinglé par digest |

Le détail par service — image, tag, digest, commande, réseaux, volumes, ports
publiés, healthcheck, dépendances, variables requises — est dans
[`artifacts/g0/inventory.json`](../../artifacts/g0/inventory.json).

## 4. Surfaces d'entrée — 246 au total

**OpenAPI n'en décrit que 231.** S'y limiter aurait laissé 15 portes hors
inventaire.

| Catégorie | Nombre |
| --- | --- |
| Opérations documentées dans l'OpenAPI | 231 |
| Routes runtime totales | **239** |
| — dont **hors OpenAPI** | **8** |
| — dont WebSockets | **1** |
| — dont montages / fichiers statiques | **1** |
| Surfaces **non HTTP** | **7** |
| **TOTAL** | **246** |

Détail : [`ROUTES.md`](ROUTES.md) et
[`artifacts/g0/entrypoints.json`](../../artifacts/g0/entrypoints.json).

## 5. Données

Base PostgreSQL **16.14**, migrée jusqu'à `20260826_0043` avant introspection.

| Objet | Nombre |
| --- | --- |
| Schémas | 1 (`public`) |
| Tables | **49** |
| Colonnes | **519** |
| Clés primaires | 49 |
| Clés étrangères | **56** |
| Contraintes UNIQUE | 26 |
| Contraintes CHECK | 3 |
| Index | **170** |
| Séquences | 48 |
| Enums | 1 |
| Extensions | 1 |
| Vues / vues matérialisées | **0** |
| Fonctions / triggers | **0 / 0** |
| Politiques RLS | **0** |

Détail : [`SCHEMA.md`](SCHEMA.md).

> **Zéro politique RLS**, et c'est cohérent : le cloisonnement est appliqué
> dans l'application, pas dans la base. Le lot B devra dire si cela suffit — le
> constater ici ne le valide pas.

## 6. Frontières externes — requalification du chiffre de 14

Le comptage préliminaire cherchait `httpx|requests|urllib` dans `app/` : il
comptait des **imports**, pas des frontières. Un module qui importe `httpx`
sans jamais sortir du réseau y figurait ; une frontière ouverte par un
navigateur ou une imprimante n'y figurait pas.

Les frontières réelles, avec leur état par défaut :

| Frontière | Protocole | État par défaut | Où |
| --- | --- | --- | --- |
| **CSA / Supabase** | HTTPS | **désactivée** (`CSA_SYNC_ENABLED=false`) | `app/services/csa_*` |
| **ONMCI** | HTTPS | fail-closed | `app/services/onmci_client.py` |
| **Webhooks sortants** | HTTPS | selon configuration | transport centralisé, anti-SSRF |
| **Automate DH36** | TCP entrant | **désactivée** (`ENABLE_DH36_LISTENER=false`) | `analyzer-gateway` |
| **Trames brutes automates** | TCP entrant | **désactivée** | `analyzer-gateway` |
| **Prometheus** | HTTP interne | active | scrape `/metrics`, bloqué au proxy |
| **Sauvegardes** | système de fichiers | active | `db-backup`, dump vérifié |
| **Navigateur → CDN** | HTTPS depuis le **poste client** | active | Leaflet, JsBarcode |
| **Navigateur → tuiles OSM** | HTTPS depuis le **poste client** | active | `ehm_map.html` |
| **Registres logiciels** | HTTPS | build uniquement | GHCR, PyPI, Docker Hub |
| **Grafana** | HTTP interne | **overlay optionnel** | absent du cœur |
| **Imprimante** | — | **non instrumentée** | impression navigateur |

> **Recouvrements et ce qu'ils expliquent.** Les 12 modules « CSA » et les 4
> modules « ONMCI » du comptage préliminaire se recoupent : plusieurs modules
> touchent aux deux, et beaucoup ne font aucun appel — ils importent des
> schémas ou des types. Le chiffre de 14 était un artefact de méthode.
>
> **Le lot B détaillera les données transportées.** Le lot A s'arrête aux
> frontières techniques.

## 7. Ce que cet inventaire ne dit pas

- **Il ne juge pas.** Une route non authentifiée y figure telle quelle,
  qualifiée par écrit dans
  [`ROUTE_EXPOSURE_QUALIFICATION.json`](ROUTE_EXPOSURE_QUALIFICATION.json),
  jamais corrigée en silence.
- **Il ne couvre pas les données sensibles ni la matrice RBAC** — lot B.
- **Il ne mesure ni la couverture ni la performance** — lot C.
- **Il ne prononce aucun statut de gouvernance.** `REAL_DATA_NO_GO` et
  `DISTRIBUTION_NO_GO` sont inchangés.

## 8. Reproduire ces preuves

Une preuve qu'on ne peut pas refaire n'est pas une preuve. Sur le même commit,
ces commandes doivent produire des octets identiques à ceux versionnés.

```bash
# 1. Une base PostgreSQL vierge, puis migrée — jamais la base d'un site.
docker run -d --name g0-pg -p 127.0.0.1:55432:5432 \
  -e POSTGRES_USER=ruggylab -e POSTGRES_PASSWORD=g0_synthetic_pw \
  -e POSTGRES_DB=g0_baseline postgres:16-alpine
export DATABASE_URL=postgresql+psycopg://ruggylab:g0_synthetic_pw@127.0.0.1:55432/g0_baseline
alembic upgrade head

# 2. Contrôle : échoue si les artefacts versionnés ont dérivé.
python scripts/g0_inventory.py --check
python scripts/g0_schema_inventory.py --database-url "$DATABASE_URL" --check

# 3. Mise à jour délibérée, si le code a réellement changé.
python scripts/g0_inventory.py --generate
python scripts/g0_schema_inventory.py --database-url "$DATABASE_URL" --generate
```

Le job CI **`G0 — Architecture and data baseline`** exécute la même séquence à
chaque `push` et à chaque pull request. Il **ne régénère jamais les artefacts
tout seul** : mettre à jour la baseline reste une modification tracée, relue,
dont l'auteur répond. Une régénération automatique et silencieuse rendrait le
contrôle décoratif — le fichier suivrait toujours le code, et ne dirait plus
jamais rien.

Les champs volatils — heure de génération, SHA de la source, plateforme —
vivent à part, dans `provenance.json` et `schema-provenance.json`. Les laisser
dans le corps comparé produirait un diff à chaque exécution : le contrôle
échouerait toujours, on finirait par l'ignorer.
