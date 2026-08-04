# RuggyLab OS — Dossier d'architecture pour revue externe

Document destiné à une revue par des ingénieurs/architectes et par IA.
Objectif : présenter l'état réel du système, avec un focus **Architecture réseau**
et **Intégration LIS (Système d'Information de Laboratoire)**. État au head
migration `0035`.

> RuggyLab OS est un **SIL (LIS)** clinique pour un laboratoire d'analyses
> médicales en Côte d'Ivoire (contexte CMU/FCFA, établissement militaire/Garde
> Républicaine), conçu pour fonctionner en environnement à ressources contraintes
> (coupures électriques, connectivité intermittente).

---

## 1. Synthèse exécutive

| Dimension | Valeur (vérifiable dans le dépôt) |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Base de données | PostgreSQL 16 (prod) / SQLite (dev, tests) |
| Cache / temps réel | Redis 7 (cache, rate-limit, fan-out), WebSocket |
| Frontend | Application mono-page (`/app`), JS externalisé et mis en cache |
| API | REST `/api/v1` — ~212 routes ; ~44 tables ; ~26 000 LOC (app) |
| Auth | JWT (access + refresh), révocation par `jti`, mots de passe pbkdf2_sha256 |
| Observabilité | Prometheus + Grafana, logs structurés, request-id |
| Qualité | ~1 150 tests ; CI : ruff, mypy, bandit, pytest, **migrations PostgreSQL**, CodeQL, **E2E Playwright**, build image |
| Conteneurisation | Docker / docker-compose (app, postgres, redis, prometheus, grafana, migrate) |

**Périmètre fonctionnel** : dossier patient & prescription d'examens (« le fil »),
paillasse & résultats (flags HH/H/N/L/LL, delta-check, valeurs critiques,
auto-validation ISO 15189 §5.8, 3 moteurs d'interprétation), comptes-rendus PDF
(par résultat et consolidés, signature électronique, versions/snapshots),
stocks & réactifs (CMM, prédiction, **lots FEFO**), comptabilité CMU
(facturation CNAM 70/30, reçus, avoirs, BNPL, créances âgées, export comptable),
épidémiologie + **notifications MADO** au district, **registre AES** (sécurité
personnel), qualité NC/CAPA, audit, **RBAC par rôle et par unité**.

---

## 2. Architecture logique

```
Navigateur (cockpit /app, JS statique mis en cache)
        │ HTTPS (REST /api/v1 + WebSocket notifications)
        ▼
Reverse proxy TLS  ──►  Application FastAPI (uvicorn, :8000)
                              │            │            │
                              ▼            ▼            ▼
                        PostgreSQL 16   Redis 7    Bus de notifications
                        (:5432)         (:6379)    (WS / fan-out Redis)
```

- **Middlewares** (ordre) : SecurityHeaders, RequestID, LoginRateLimit,
  UserQuota, RateLimit, Compression, Observability, PoweredBy.
- **Cloisonnement RBAC** : rôles `technician / officer / accountant / admin` +
  périmètre par **unité** (patients, résultats, prescriptions, imagerie, POCT
  scopés ; comptable interdit du clinique côté backend).
- **Migrations** : chaîne Alembic linéaire (head `0035`), idempotentes.
- **Couplage faible** : les modules récents (AES, notifications MADO, lots) sont
  des fichiers/tables isolés branchés sur l'`api_router`.

---

## 3. Architecture réseau (concret)

### 3.1 Segmentation recommandée (VLAN / sous-réseaux)
| Zone | Contenu | Règles |
|---|---|---|
| **DMZ / proxy** | Reverse proxy TLS (Caddy/Nginx/Traefik) | Seul **443** exposé côté utilisateurs ; redirige vers app:8000 |
| **VLAN serveurs** | App FastAPI, PostgreSQL, Redis | PostgreSQL/Redis **non exposés** hors VLAN ; accès app uniquement |
| **VLAN postes cliniques** | Accueil, paillasses, validation, comptabilité | Accès HTTPS au proxy uniquement |
| **VLAN automates** | DH36, Magnus Theia-i, Precis Expert (+ convertisseurs série→Ethernet) | Sortie autorisée **uniquement** vers l'endpoint d'ingestion de l'app |
| **VLAN management** | Prometheus (:9090), Grafana (:3000), supervision | Restreint aux administrateurs |

### 3.2 Flux et ports
- Externe → Proxy : `443/tcp` (TLS). Interne Proxy → App : `8000/tcp`.
- App → PostgreSQL `5432/tcp`, App → Redis `6379/tcp` (internes).
- Automates → App : `POST /api/v1/analyzer/results` (clé API + signature HMAC +
  **allowlist IP**) ; instruments legacy via **convertisseur série→IP** (type Moxa).
- App → Internet (sortant, optionnel) : sauvegarde hors-site, notification district.

### 3.3 Résilience (contexte coupures / connectivité)
- **Onduleurs (UPS)** sur serveur **et** postes critiques (corruption = perte).
- **Internet de secours 4G** pour MADO + backup hors-site ; le LAN reste
  autonome (le labo fonctionne **sans** Internet).
- **Sauvegarde PostgreSQL** quotidienne (`scripts/pg_backup.ps1`) + restauration
  **vérifiée sur base scratch** (`scripts/pg_restore_verify.ps1`) ; copie hors-site
  hebdomadaire.
- **Mode dégradé** documenté : registre/cahier papier puis ressaisie.

### 3.4 Pistes de haute disponibilité (à arbitrer)
- MVP : serveur unique. Évolutions : réplication PostgreSQL (streaming),
  2+ réplicas app derrière le proxy, Redis persistant (AOF) déjà activé.

### 3.5 Schéma de zones (textuel)
```
[Internet]──443──[Reverse proxy TLS]──[VLAN serveurs: App─DB─Redis]
                                          ▲
[VLAN postes cliniques]──HTTPS────────────┤
[VLAN automates]──série→IP / API HMAC─────┘   (ingestion uniquement)
[VLAN management]──Prometheus/Grafana────── (admin)
```

---

## 4. Intégration LIS / interopérabilité (concret)

RuggyLab **est** le LIS. Quatre axes d'intégration, du plus mûr au plus ouvert :

### 4.1 Instruments → LIS (le plus mûr)
- **Ingestion automates** : `POST /api/v1/analyzer/results` — sécurisé par
  **clé API** (comparaison constante), **signature HMAC** horodatée (anti-rejeu)
  et **allowlist IP**. Idempotence par identifiant de message.
- **DH36 / HL7-like** : `POST /api/v1/dh36/ingest` — parse le message brut,
  déduplique via `message_control_id`, rattache au résultat.
- **POCT** (Precis Expert, POCT1-A) : `POST /api/v1/results/precis-expert`.
- **Imagerie** (microscope Magnus Theia-i) : capture → analyse IA paludisme.
- Cible standard : **ASTM E1381/E1394** via middleware d'interfaçage (driver TCP
  fourni `scripts/astm_tcp_driver.py`).

### 4.2 LIS ↔ HIS / DPI (à formaliser)
- **Aujourd'hui** : API REST JSON `/api/v1` (patients, prescriptions, résultats),
  **export FHIR R4** des résultats/patients, comptes-rendus PDF.
- **Recommandation** : passerelle **HL7 v2** (ADT pour démographie patient
  entrante ; ORM pour les demandes ; ORU pour les résultats sortants) **ou**
  **FHIR R4** (`ServiceRequest`, `DiagnosticReport`, `Observation`, `Patient`).
  Point d'identité : `ipp_unique_id` + code-barres échantillon + **n° labo**.

### 4.3 LIS → Santé publique
- **Notifications MADO** : `epi-notifications` (pathologie + **quartier de
  résidence** pour cartographie) avec statut de transmission au district.
- Exports épidémiologiques CSV.

### 4.4 LIS ↔ Pharmacie
- **FHIR R4 Pharmacy** (`/api/v1/...fhir...`), facturation CMU (CNAM/ticket
  modérateur), DCI/CIM-10.

### 4.5 Vocabulaires & standards
| Domaine | Standard utilisé |
|---|---|
| Examens | **LOINC** (catalogue d'examens) + codes internes, table de correspondance |
| Diagnostics | **CIM-10** (facturation, épidémio) |
| Médicaments | **DCI** (OMS) |
| Échange clinique | **FHIR R4** (export), cible **HL7 v2** pour HIS |
| Instruments | **ASTM E1381/E1394**, POCT1-A, HL7-like (DH36) |

### 4.6 Formats d'échange
JSON (REST), **FHIR R4**, CSV (exports comptables/épidémio), **PDF** (comptes-rendus,
reçus). Tous les imports sont **authentifiés, idempotents et audités**.

---

## 5. Sécurité (posture actuelle)
- JWT + révocation `jti` ; pbkdf2_sha256 ; **rate-limit login** + quotas.
- En-têtes de sécurité (CSP/HSTS/X-Frame…) ; CORS par origines explicites.
- **RBAC par rôle + unité** ; séparation des tâches (comptable ≠ clinique).
- WebSocket authentifié par sous-protocole (jeton hors URL).
- Ingestion automates : clé API + HMAC + allowlist IP.
- Audit applicatif des actions sensibles ; CSV protégé contre l'injection.
- CI : bandit + CodeQL + `pip-audit`/`detect-secrets` (advisory).
- Gestion des secrets : variables d'env / gestionnaire (`docs/SECRETS_MANAGEMENT.md`),
  contrôle `scripts/check_deploy_readiness.py`.

---

## 6. Limites connues / sujets soumis à la revue
1. **Frontend mono-page** (~430 Ko à l'origine, JS désormais externalisé/caché) —
   pas de framework SPA ; arbitrer une migration (React/Vue) vs maintien.
2. **HL7 v2 non encore implémenté** pour l'intégration HIS (FHIR partiel) — à
   prioriser selon l'écosystème hospitalier cible.
3. **Haute disponibilité** : mono-serveur par défaut ; réplication DB/app à cadrer.
4. **Lots FEFO** : ledger lot dédié ; l'auto-consommation par lot à la production
   d'un résultat n'est pas encore branchée sur la consommation automatique.
5. **i18n** : interface en français uniquement.
6. **Scalabilité** : dimensionnée pour un établissement ; volumétrie multi-sites
   à évaluer (partitionnement, archivage).

## 7. Questions pour les relecteurs
- Architecture réseau : segmentation/zonage proposé adéquat pour un site unique
  à connectivité intermittente ? Recommandations HA réalistes à faible coût ?
- Intégration : HL7 v2 vs FHIR R4 comme passerelle HIS prioritaire dans le
  contexte ivoirien ? Conformité aux normes nationales de santé numérique ?
- Sécurité : la posture (RBAC unité, HMAC ingestion, audit) est-elle suffisante
  pour des données cliniques sous réglementation locale ?
- Conception : le couplage modules/`api_router` et la stratégie de migrations
  tiennent-ils à l'échelle ?

---

*Annexes utiles : `docs/DEPLOYMENT.md`, `docs/INTERPRETATION.md`,
`docs/LIVRABLES_FORMATION_EXPLOITATION.md`, `docs/observability.md`,
`docs/SECRETS_MANAGEMENT.md` ; CI : `.github/workflows/ci.yml`.*
