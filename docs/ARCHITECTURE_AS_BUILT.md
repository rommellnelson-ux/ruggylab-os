# RuggyLab OS — Architecture telle que construite (as-built)

> Ce document décrit **le système réellement livré**, pas la cible. Chaque
> affirmation porte un statut. Mettre à jour à chaque PR qui change
> l'architecture, les ports, les migrations ou les procédures.

- **Version applicative** : 0.1.0
- **Head Alembic** : `20260724_0039` (chaîne linéaire)
- **Dernière mise à jour** : 2026-07-24 (fail-closed appareils, PR #107)
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
| `analyzer-gateway` | `python -m app.analyzer_gateway` | Héberge les interfaces explicitement qualifiées ; aucune par défaut ; heartbeat de process | VERIFIED (tests + compose), interfaces DISABLED |
| `all` (défaut) | `uvicorn app.main:app` | Tout-en-un (dev / mono-poste) | VERIFIED |

Le rôle est loggé au démarrage. **Aucune tâche singleton ne tourne dans les
workers web** quand `PROCESS_ROLE=web` (cf. `tests/test_process_role_and_metrics.py`).

## 3. Services et réseau (docker-compose)

| Service | Image | Ports publiés | Réseaux |
|---|---|---|---|
| `proxy` (Caddy) | caddy:2.8-alpine | **80, 443 — seuls ports publiés** | frontend |
| `app` | ruggylab-os | aucun | frontend, backend |
| `scheduler` | ruggylab-os | aucun | backend |
| `analyzer-gateway` | ruggylab-os | aucun ; aucune interface activée dans le compose de référence | analyzer, backend |
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

- Chaîne Alembic linéaire jusqu'à `20260724_0039` — **VERIFIED** : `upgrade head`
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
- Planification quotidienne : **livrée** — service compose `db-backup`
  (`pg_dump -Fc` + SHA-256, rétention, healthcheck de fraîcheur < 26 h) ;
  production d'un dump vérifiée en CI (`docker-stack`). La **copie hors-site**
  du répertoire reste une tâche d'exploitation — CONFIGURED.
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
| Ingestion/listener DH36 | DISABLED par défaut ; protocole et appareil réels non qualifiés |
| MFA (TOTP/WebAuthn) pour comptes privilégiés | TARGET (P1) |
| Audit append-only (table `audit_events` existante, non immuable) | IMPLEMENTED / TARGET durcissement |
| Scopes OAuth | DECLARATIF : aucune route scopée ; les rôles DB font autorité |
| Pin des Actions par SHA et runtime Node 24 | VERIFIED (CI, PR #100) |
| SBOM et signature d'images | TARGET (P1) |

## 9. Interfaçage automates

- Le gateway reste sain grâce à un heartbeat, mais n'ouvre aucune interface
  dans le compose de référence — **VERIFIED**, PR #107.
- Le listener et l'endpoint historiques **Dymind DH36/HL7** sont implémentés et
  testés sur trames synthétiques, mais désactivés par défaut. Leur correspondance
  avec le DH36 réel n'est pas démontrée — **IMPLEMENTED / NON QUALIFIÉ**.
- Les parseurs bruts Dymind hématologie, Dymind biochimie et Anbio immuno ont
  `protocol="unknown"` et lèvent `NotImplementedError` — **STUB / DISABLED**.
- Le driver ASTM TCP (`scripts/astm_tcp_driver.py`) est générique, non rattaché
  à un appareil qualifié et non éprouvé en réel — **IMPLEMENTED / UNKNOWN**.
- Les routes POCT/Precix sont fail-closed tant que le registre `Equipment` ne
  peut pas porter un profil qualifié — **VERIFIED**.
- Inventaire, statuts et tests :
  `DEVICE_CONNECTIVITY_INVENTORY_2026.md`,
  `DEVICE_INTEGRATION_MATRIX_2026.md` et
  `DEVICE_COMMISSIONING_CHECKLIST_2026.md`.

## 10. Interprétation et auto-validation

- Intervalles de référence versionnés (`biological_reference_ranges`), delta
  checks, valeurs critiques, mappings de codes : IMPLEMENTED + tests.
- Auto-validation (§5.8 ISO 15189) : configuration versionnée + garde-fous —
  IMPLEMENTED + tests (`test_auto_validation.py`). **La présence de cette
  fonction ne vaut pas conformité ISO 15189** (preuves organisationnelles
  requises). Traçabilité : `docs/AUTOVALIDATION_5_8.md`.
- Moteur d'interprétation **unique (§21) — DÉCISION CONFIRMÉE (2026-07, responsable
  du projet) : NE PAS unifier.** `ReferenceRange`/`CriticalRange` reste le moteur
  officiel, `bioref` la couche d'aide (cf. `docs/INTERPRETATION.md`, section
  « Décision d'architecture (figée) »). L'unification totale a été écartée : gain
  surtout esthétique pour un risque clinique réel (migration du moteur de
  validation). **Divergence assumée et close** avec le §21 des Instructions
  maîtres — ce n'est donc PAS une limitation ouverte mais un choix arrêté.

## 11. Limitations connues / non implémenté

- **Gouvernance clinique — RISQUE ASSUMÉ** : `REQUIRE_VALIDATION_FOR_RELEASE=false`
  en production (compose et `.env.example`). **Décision explicite du responsable
  du laboratoire (2026-07-08)** : les comptes-rendus sont libérés sans validation
  biologique obligatoire, faute d'un biologiste validateur en poste ; les valeurs
  critiques restent acquittées. **Condition de réversibilité : basculer à `true`
  dès l'affectation d'un biologiste validateur.** La procédure « provisoire »
  formelle (rôle, motif, filigrane, file d'attente, délai maximal — §22) n'est
  pas implémentée à ce jour (TARGET).
- **Serveur physique non qualifié** : la stack tourne en CI (job `docker-stack`)
  mais n'a jamais été démarrée sur le serveur cible du laboratoire (UPS, VLAN
  automates, imprimantes) — UNKNOWN.
- **Interfaces appareil non qualifiées** : aucune n'est connectée à un appareil
  réel. Le compose les désactive et ne publie aucun port instrument. Activation
  interdite sans identité, manuel, protocole, mapping et commissioning signés.
- **PR80-CLIN-01 corrigé techniquement** : qualitatif non validé/non critique,
  POCT refusé et aucune clôture/valeur/seuil implicite. Le workflow futur reste
  soumis à décision clinique.
- **Paludisme fail-closed** : aucun fallback heuristique ; modèle absent ou
  erreur = échec explicite ; une éventuelle inférence ne modifie pas `Result`.
  Le modèle réel et son usage clinique restent non qualifiés.
- **Registre Equipment normalisé** : identité nullable, interfaces,
  qualifications, analytes et documents sont portés par la révision 0039. Le
  service central vérifie snapshot, preuve, périmètre et RBAC à l'activation et
  à l'ingestion. Aucune donnée réelle n'est préremplie ; commissioning requis.
- **Worker Windows local incompatible** : la tâche observée passe un argument
  absent de la CLI courante et pointe vers un checkout mutable. Elle ne doit pas
  être utilisée comme preuve du rôle outbox préproduction ; voir
  `docs/INCIDENT_WORKER_PLANIFIE_2026-07-23.md`.
- **Prometheus/Grafana « accès VPN/bastion »** : le réseau management existe,
  mais aucun VPN/bastion n'est livré par le dépôt — TARGET (accès via
  `docker exec` local en attendant).
- **Multi-worker non testé en intégration** (le gating par rôle est testé
  unitairement ; `docker-stack` valide 1 exemplaire par rôle, pas le scaling).
- **Heartbeats scheduler/gateway** : implémentés et contrôlés par les
  healthchecks compose — VERIFIED en CI ; supervision réelle du serveur cible à
  qualifier.
- `/docs`, `/openapi.json`, `/metrics`, `/redoc` : **bloqués au proxy (404,
  VERIFIED en CI)** ; côté app ils restent servis sur le réseau backend (choix :
  Prometheus y scrape `/metrics`). Restriction applicative fine (§14) — TARGET.
- Corrigés par le lot P1 (VERIFIED en CI via `docker-stack` et tests) :
  confiance proxy (`TRUSTED_PROXY_IPS` = IP statique de Caddy), cardinalité
  métriques (label = gabarit de route, « unmatched » pour les 404), verrou de
  migration au démarrage, sauvegarde automatisée (`db-backup` + healthcheck de
  fraîcheur < 26 h).
- Versionnement immuable des résultats validés (§20) : statuts de correction
  existent, pas de chaîne `version/previous_version_id` — TARGET.
- FHIR : export partiel (« sous-ensemble FHIR R4 »), pas d'API FHIR complète.
- HL7 v2 ADT/ORM/ORU génériques, multisite, PRA : PLANNED (P1/P2).

## 12. Registre Equipment

La révision `20260724_0039` ajoute les tables `equipment_interfaces`,
`equipment_qualifications`, `equipment_approved_analytes` et
`equipment_documents`. Une migration ne crée aucune interface, qualification,
méthode, unité, analyte ou preuve.

`app.services.equipment_registry` porte la seule transition d'activation et
ajoute l'audit avant le commit. Les mutations techniques et l'activation
utilisent `require_admin`; l'approbation, la suspension et la désactivation
utilisent `require_officer`. Approbation et activation sont deux actes
distincts, sans exigence actuelle de deux personnes.

L'activation du registre ne démarre aucun listener. Tous les appareils réels
restent **NON QUALIFIÉS / NON ACTIVABLES EN CLINIQUE**.

## 13. Références

- Déploiement, sauvegarde, rollback : `docs/DEPLOYMENT.md`
- Secrets : `docs/SECRETS_MANAGEMENT.md` · Observabilité : `docs/observability.md`
- Exploitation/formation, mode dégradé, UPS : `docs/LIVRABLES_FORMATION_EXPLOITATION.md`
- Décision moteur d'interprétation : `docs/INTERPRETATION.md`
- Garde-fous auto-validation : `docs/AUTOVALIDATION_5_8.md`
- Revue d'intégration PR #80 : `docs/PR80_MAIN_INTEGRATION_REVIEW_2026.md`
- Qualification préproduction : `docs/PREPRODUCTION_QUALIFICATION_PLAN_2026.md`
- Rollback et reprise : `docs/ROLLBACK_AND_RECOVERY_RUNBOOK_2026.md`
- Parc équipements : `docs/DEVICE_CONNECTIVITY_INVENTORY_2026.md`
- Matrice d'intégration : `docs/DEVICE_INTEGRATION_MATRIX_2026.md`
- Décision de registre : `docs/DEVICE_EQUIPMENT_REGISTRY_DECISION_2026.md`
- Architecture du registre : `docs/EQUIPMENT_REGISTRY_ARCHITECTURE_2026.md`
- Dictionnaire : `docs/EQUIPMENT_REGISTRY_DATA_DICTIONARY_2026.md`
- Workflow : `docs/EQUIPMENT_QUALIFICATION_WORKFLOW_2026.md`
