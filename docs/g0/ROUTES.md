# G0 — Surfaces d'entrée

> **246 surfaces, dont 231 seulement dans l'OpenAPI.** Un inventaire limité au
> contrat documenté aurait laissé 15 portes hors champ.
>
> Généré par [`scripts/g0_inventory.py`](../../scripts/g0_inventory.py) depuis
> **deux sources** : l'OpenAPI que l'application produit réellement, et son
> arbre de routage Starlette. Ni l'une ni l'autre ne suffit seule — l'OpenAPI
> ignore les WebSockets et les montages, l'arbre ignore les schémas.

## 1. Vue d'ensemble

| Catégorie | Nombre |
| --- | --- |
| Chemins OpenAPI | 198 |
| Opérations OpenAPI | **231** |
| Routes runtime | **239** |
| — hors OpenAPI | **8** |
| — WebSockets | 1 |
| — montages / fichiers statiques | 1 |
| Surfaces non HTTP | **7** |
| **TOTAL** | **246** |

## 2. Exposition des 231 opérations HTTP

Le classement est **dérivé des dépendances FastAPI réelles** de chaque route,
via `get_flat_dependant`. Le champ `securitySchemes` de l'OpenAPI est global :
s'y fier aurait classé les 231 opérations comme authentifiées, y compris celles
qui ne le sont pas.

| Classe | Nombre | Signification |
| --- | --- | --- |
| `AUTHENTICATED` | **182** | dépendance `OAuth2PasswordBearer` |
| `ADMIN_ONLY` | **33** | authentification + garde de rôle |
| `PUBLIC` | **6** | aucune dépendance de sécurité |
| `A_QUALIFIER` | **6** | ni garde reconnue, ni classement évident |
| `INTERNAL` | **4** | sondes de santé |

> **`A_QUALIFIER` est délibérément conservé.** Une route dont on ne peut pas
> dire si elle est protégée doit être examinée, pas rangée par défaut du côté
> rassurant. Les douze routes `PUBLIC` et `A_QUALIFIER` sont qualifiées une par
> une dans
> [`ROUTE_EXPOSURE_QUALIFICATION.json`](ROUTE_EXPOSURE_QUALIFICATION.json), et
> un test échoue si l'une d'elles n'y figure pas.

### Les six routes `PUBLIC`

`/` · `/app` · `/app/bench` · `/app/express` · `/app/map` · `/app/microscopy`

Ce sont des **gabarits HTML statiques** : les données affichées proviennent
d'appels API authentifiés faits par le navigateur. Sans jeton, l'interface
reste vide.

**Un point classé P1** : `/app/map` sert la cartographie d'établissements
militaires. Le gabarit ne contient aucune coordonnée — elles viennent de
`/api/v1/military-facilities`, qui exige un jeton — mais l'existence de la page
révèle la fonctionnalité. À examiner avant tout déploiement exposé.

### Les six routes `A_QUALIFIER`

| Route | Constat | Classement |
| --- | --- | --- |
| `POST /api/v1/analyzer/results` | garde propre `_verify_analyzer_security`, non reconnue par les marqueurs — **pas une route ouverte** | P2 |
| `GET /api/v1/health` | sonde, doit répondre avant l'authentification | P2 |
| `POST /api/v1/login/access-token` | route qui *délivre* l'authentification — circulaire de l'exiger ; protégée par rate limiting | P2 |
| `POST /api/v1/login/logout` | **aucune dépendance déclarée** — comportement effectif à confirmer | **P1** |
| `POST /api/v1/login/refresh` | le jeton de rafraîchissement fait office d'authentification | **P1** |
| `GET /api/v1/reports/verify/{token}` | vérification de QR code : le jeton **est** l'autorisation | **P1** |

Aucune n'est corrigée ici. Quatre partent au backlog du lot D.

## 3. Les 8 routes hors OpenAPI

| Type | Chemin | Méthodes |
| --- | --- | --- |
| **WebSocketRoute** | `/api/v1/notifications/ws` | `WEBSOCKET` |
| **StaticFiles** | `/static` | — |
| APIRoute | `/metrics` | `GET` |
| APIRoute | `/{path_name:path}` | `OPTIONS` |
| Route | `/docs` | `GET`, `HEAD` |
| Route | `/docs/oauth2-redirect` | `GET`, `HEAD` |
| Route | `/openapi.json` | `GET`, `HEAD` |
| Route | `/redoc` | `GET`, `HEAD` |

Quatre d'entre elles — `/metrics`, `/docs`, `/redoc`, `/openapi.json` — sont
**bloquées au proxy** : le job CI `docker-stack` vérifie qu'elles renvoient 404
à travers Caddy. Elles restent joignables sur le réseau interne, ce qui est
voulu pour la collecte Prometheus.

> **Deux surfaces méritent l'attention du lot B**, et n'apparaissaient dans
> aucun comptage préalable :
>
> - le **WebSocket** `/api/v1/notifications/ws` — un canal temps réel dont
>   l'authentification ne se lit pas dans l'OpenAPI ;
> - la route **catch-all** `/{path_name:path}` en `OPTIONS`, qui répond à
>   n'importe quel chemin. Vraisemblablement le pré-vol CORS ; à confirmer.

## 4. Les 7 surfaces non HTTP

| Surface | Type | Déclencheur | État par défaut | Exposition réseau |
| --- | --- | --- | --- | --- |
| `scheduler` | processus | périodique | activé | aucune |
| `analyzer-gateway` | processus | démarrage | activé, **interfaces désactivées** | aucun port publié |
| listener DH36 | TCP entrant | `ENABLE_DH36_LISTENER=true` | **désactivé** | `ANALYZER_BIND_IP`, jamais `0.0.0.0` |
| listener trames brutes | TCP entrant | `ANALYZER_RAW_LISTENER_ENABLED=true` | **désactivé** | `ANALYZER_BIND_IP` |
| migrations Alembic | tâche unique | profil `migrate`, manuel | manuel | aucune |
| sauvegarde PostgreSQL | tâche planifiée | service `db-backup` | activée | aucune |
| collecte Prometheus | cible de scrape | Prometheus interroge | activée | interne, bloquée au proxy |

Chacune porte son type, son déclencheur, son état par défaut, son exposition,
sa garde et les données qu'elle manipule — voir
[`artifacts/g0/entrypoints.json`](../../artifacts/g0/entrypoints.json).

## 5. Ce qui reste au lot B

Le lot A dit **quelles** surfaces existent et **comment** elles sont gardées.
Il ne dit pas **qui** peut faire quoi : la matrice rôles × opérations, la
nature exacte des données traversées, et la confirmation du comportement des
trois routes `login/*` relèvent du lot B.
