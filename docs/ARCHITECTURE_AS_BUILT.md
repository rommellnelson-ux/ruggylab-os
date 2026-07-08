# RuggyLab OS — Architecture telle que construite (as-built)

> Ce document décrit **le système réellement livré**, pas la cible. Chaque
> affirmation porte un statut. Mettre à jour à chaque PR qui change
> l'architecture, les ports, les migrations ou les procédures.

- **Version applicative** : 0.1.0
- **Head Alembic** : `20260625_0036` (36 migrations, chaîne linéaire)
- **Dernière mise à jour** : 2026-07-08 (post PR #55)
- **Périmètre** : mono-site, LAN de laboratoire, fonctionnement sans Internet

## Statuts utilisés

```text
VERIFIED      = présent et prouvé (test automatisé, CI, ou exécution documentée)
IMPLEMENTED   = présent dans le code, non prouvé en conditions réelles
CONFIGURED    = prévu dans les fichiers de configuration, jamais exécuté en réel
TARGET        = cible recommandée, non implémentée
PLANNED       = fonctionnalité future
UNKNOWN       = impossible à confirmer
```

## 1. Vue d'ensemble

Monolithe modulaire **FastAPI / SQLAlchemy / Alembic** :

```text
app/api/v1/endpoints (52 modules, ~199 routes)  → contrôle d'accès + validation
app/schemas                                     → contrats Pydantic
app/services                                    → logique métier
app/models (44 tables)                          → persistance
```

- Base de données : **PostgreSQL 16** en production, SQLite en développement/tests.
- Cache & fan-out temps réel : **Redis 7** (backend `memory` en dev).
- Frontend : cockpit HTML/JS servi par l'app (pas de framework SPA — choix assumé,
  cf. §31 des Instructions maîtres).

## 2. Architecture d'exécution (rôles de process)

Depuis le commit `64e228c`, chaque process déclare un rôle via `PROCESS_ROLE` :

| Rôle | Entrypoint | Responsabilités | Statut |
|---|---|---|---|
| `web` | `uvicorn app.main:app` | API/UI, WebSocket, fan-out Redis (dans **chaque** worker) | VERIFIED (tests de gating) |
| `scheduler` | `python -m app.scheduler` | Purge des jetons (1 h) — exemplaire unique | VERIFIED (tests) / CONFIGURED (runtime compose) |
| `analyzer-gateway` | `python -m app.analyzer_gateway` | Listener DH36 (bind TCP → exemplaire unique) | VERIFIED (tests) / CONFIGURED (runtime compose) |
| `all` (défaut) | `uvicorn app.main:app` | Tout-en-un (dev / mono-poste) | VERIFIED |

Le rôle est loggé au démarrage. **Aucune tâche singleton ne tourne dans les
workers web** quand `PROCESS_ROLE=web` (cf. `tests/test_process_role_and_metrics.py`).

## 3. Services et réseau (docker-compose)

| Service | Image | Ports publiés | Réseaux |
|---|---|---|---|
| `proxy` (Caddy) | caddy:2.8-alpine | **80, 443 — seuls ports publiés** | frontend |
| `app` | ruggylab-os | aucun | frontend, backend |
| `scheduler` | ruggylab-os | aucun | backend |
| `analyzer-gateway` | ruggylab-os | aucun (port DH36 à lier au VLAN automates si besoin) | analyzer, backend |
| `postgres` | postgres:16-alpine | aucun | backend |
| `redis` | redis:7-alpine | aucun | backend |
| `prometheus` | prom/prometheus | aucun (accès VPN/bastion) | backend, management |
| `grafana` | grafana:11.0.0 | aucun (accès VPN/bastion) | management |
| `migrate` | ruggylab-os | run-once manuel (`--profile migrate`) | backend |

- TLS : Caddy, CA interne par défaut (LAN sans Internet) ; ACME/certificats
  fournis en option (`deploy/Caddyfile`). — **VERIFIED en CI** : le job
  `docker-stack` construit l'image, démarre `docker-compose.yml` seul, vérifie
  que **seuls 80/443 sont publiés**, que scheduler/gateway sont sains, et joue
  le flux clinique **à travers le proxy TLS**. Reste à éprouver sur le serveur
  physique du laboratoire (UNKNOWN hors CI).
- Image : artefact immuable **obligatoire** (`RUGGYLAB_IMAGE=<tag précis>`,
  le compose refuse de démarrer sans) ; la CI publie
  `ghcr.io/<owner>/<repo>:<git-sha>` et `:<ref>` — chemin aligné sur le compose.
- Dev (`docker-compose.dev.yml`) : chargé **explicitement uniquement**
  (`-f docker-compose.yml -f docker-compose.dev.yml`). L'ancien nom
  `docker-compose.override.yml` était fusionné silencieusement par Compose et
  annulait l'architecture de production (`--reload`, rôle `all` dupliquant les
  singletons, ports réouverts) — corrigé.

## 4. Données et migrations

- Chaîne Alembic linéaire jusqu'à `20260625_0036` — **VERIFIED** : `upgrade head`
  \+ idempotence (`downgrade base` → `upgrade head`) exécutés sur PostgreSQL 16
  à chaque CI.
- Enum `userrole` : valeurs minuscules partout (modèle `values_callable`,
  migration 0036 de normalisation) — **VERIFIED** sur PostgreSQL réel + CI.
- SQLite (dev) et PostgreSQL (prod) divergent par nature (types, contraintes
  d'enum) : les chemins critiques sont couverts sur PG par la CI, le reste de la
  suite tourne sur SQLite — limitation assumée.

## 5. Flux clinique

**VERIFIED en CI sur PostgreSQL 16** (job `test-postgres`, `scripts/uat_smoke.py`,
15 contrôles) : patient → échantillon → code-barres → prescription →
rattachement → résultat → fil de suivi → cloisonnement comptable (403) →
facture (arrondis FCFA) → encaissement → synthèse comptable.

Le job `deploy` (publication d'image) **exige** `test`, `test-postgres`,
`codeql` et `e2e` — un flux cassé bloque la publication (VERIFIED, PR #55).

## 6. Observabilité

- Métriques Prometheus : route ASGI **`/metrics`** sur le port applicatif —
  **VERIFIED** (test + exécution locale). Plus de serveur secondaire 8001.
- Mode multiprocess (`PROMETHEUS_MULTIPROC_DIR`) : supporté par le code —
  **CONFIGURED**, non activé par défaut (nécessaire seulement avec plusieurs
  workers uvicorn/gunicorn dans un même conteneur).
- Scrape : `monitoring/prometheus.yml` → `app:8000/metrics` — CONFIGURED.
- Logs : JSON structurés (structlog), request-id corrélé — VERIFIED (tests
  middleware).
- Healthchecks : `/health/live`, `/health/ready`, `/health` — VERIFIED (tests).
  **Limitation** : `/docs`, `/openapi.json`, `/health` détaillé et `/metrics`
  ne sont pas restreints par IP/réseau au niveau applicatif (§14) — TARGET.

## 7. Sauvegarde et restauration (PostgreSQL)

- `scripts/pg_backup.ps1` : `pg_dump -Fc` via docker compose, SHA-256, rétention,
  chiffrement optionnel, marqueur `last_success.json`.
- `scripts/pg_restore_verify.ps1` : restauration sur base scratch + 8 contrôles
  (schéma, head Alembic, comptes, volumes, smoke) + rapport + exit ≠ 0 si échec.
- **Statut : VERIFIED** sur un cluster PostgreSQL 16.4 réel (cycle complet,
  verdict SUCCÈS + contre-test négatif documentés le 2026-06-25) ; le wrapper
  `docker compose exec/cp` est CONFIGURED (émulé lors de la vérification, pas
  encore exécuté avec un vrai démon Docker).
- Copie hors-site, planification quotidienne : **procédure documentée
  (DEPLOYMENT.md §6), exécution = responsabilité exploitation** — CONFIGURED.
- Dev SQLite : `scripts/backup.ps1` / `restore.ps1` (simple copie de fichier —
  jamais pour la production).

## 8. Sécurité

| Élément | Statut |
|---|---|
| JWT access + refresh, révocation (`jti`), purge planifiée | VERIFIED (tests) |
| Headers de sécurité (CSP, HSTS, X-Frame-Options…) sur toutes réponses | VERIFIED (tests) |
| Rate limiting global + login + quotas utilisateur | VERIFIED (tests) |
| Cloisonnement par rôle/unité (RBAC) | VERIFIED (tests `*_rbac.py` + smoke 403) |
| Démarrage refusé si secrets faibles hors test | VERIFIED (tests) |
| Ingestion DH36 : HMAC, anti-rejeu, identités par appareil | TARGET (§15) |
| MFA (TOTP/WebAuthn) pour comptes privilégiés | TARGET (P1) |
| Audit append-only (table `audit_events` existante, non immuable) | IMPLEMENTED / TARGET durcissement |
| SBOM, signature d'images, pin des Actions par SHA | TARGET (P1) |

## 9. Interfaçage automates

- Listener **Dymind DH36** (HL7 sur TCP) : parsing + ingestion — IMPLEMENTED
  (tests d'ingestion) ; isolement dans le process gateway — VERIFIED (tests de
  rôle) / CONFIGURED (runtime).
- Driver ASTM TCP (`scripts/astm_tcp_driver.py`) : IMPLEMENTED, non éprouvé sur
  instrument réel — UNKNOWN en conditions réelles.
- Quarantaine formalisée des messages non appariés (§15) : TARGET.

## 10. Interprétation et auto-validation

- Intervalles de référence versionnés (`biological_reference_ranges`), delta
  checks, valeurs critiques, mappings de codes : IMPLEMENTED + tests.
- Auto-validation (§5.8 ISO 15189) : configuration versionnée + garde-fous —
  IMPLEMENTED + tests (`test_auto_validation.py`). **La présence de cette
  fonction ne vaut pas conformité ISO 15189** (preuves organisationnelles
  requises).
- Moteur d'interprétation **unique** : décision documentée de **ne pas** fusionner
  les moteurs existants (`docs/INTERPRETATION.md` — risque clinique jugé
  supérieur au gain) ; divergence assumée avec §21 des Instructions maîtres.

## 11. Limitations connues / non implémenté

- **Gouvernance clinique** : `REQUIRE_VALIDATION_FOR_RELEASE` vaut `true` en
  production (compose) mais `false` par défaut dans le code (dev). Toute
  publication « provisoire » exige une procédure écrite (rôle, motif, filigrane,
  délai maximal) — non implémentée à ce jour (TARGET).
- **Serveur physique non qualifié** : la stack tourne en CI (job `docker-stack`)
  mais n'a jamais été démarrée sur le serveur cible du laboratoire (UPS, VLAN
  automates, imprimantes) — UNKNOWN.
- **Gateway automates non connectée à un automate réel** : IMPLEMENTED dans le
  code, CONFIGURED dans compose (réseau bridge ≠ VLAN physique), NON VÉRIFIÉ
  avec des trames DH36 réelles.
- **Prometheus/Grafana « accès VPN/bastion »** : le réseau management existe,
  mais aucun VPN/bastion n'est livré par le dépôt — TARGET (accès via
  `docker exec` local en attendant).
- **Confiance proxy** : `TRUSTED_PROXY_IPS=[]` par défaut et non configuré dans
  compose → quotas par IP potentiellement mutualisés derrière Caddy — TARGET.
- **Cardinalité métriques** : le label `endpoint` reçoit le chemin brut (IDs de
  ressources inclus) au lieu du gabarit de route — violation §5 — TARGET (lot P1).
- **Multi-worker non testé en intégration** (le gating par rôle est testé
  unitairement ; `docker-stack` valide 1 exemplaire par rôle, pas le scaling).
- `/docs`, `/openapi.json`, `/metrics` non restreints applicativement ni au
  proxy (§14) — TARGET (lot P1).
- Versionnement immuable des résultats validés (§20) : statuts de correction
  existent, pas de chaîne `version/previous_version_id` — TARGET.
- FHIR : export partiel (« sous-ensemble FHIR R4 »), pas d'API FHIR complète.
- HL7 v2 ADT/ORM/ORU génériques, multisite, PRA : PLANNED (P1/P2).

## 12. Références

- Déploiement, sauvegarde, rollback : `docs/DEPLOYMENT.md`
- Secrets : `docs/SECRETS_MANAGEMENT.md` · Observabilité : `docs/observability.md`
- Exploitation/formation, mode dégradé, UPS : `docs/LIVRABLES_FORMATION_EXPLOITATION.md`
- Décision moteur d'interprétation : `docs/INTERPRETATION.md`
