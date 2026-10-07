# Gate FOUNDATION / ARCHITECTURE / MULTI-TENANCY — 2026-10-07

Programme RUGGYLAB-2027-READINESS. Lot d'architecture : **aucune migration,
aucun changement de code applicatif**. Livrables :
[ADR-001](../architecture/ADR-001-MULTI-TENANCY.md) ·
[Classification](../architecture/TENANCY_TABLE_CLASSIFICATION.md) ·
[Menaces](../architecture/TENANCY_THREAT_MODEL.md) ·
[Migration](../architecture/TENANCY_MIGRATION_PLAN.md) ·
[Matrice transverse](../architecture/TENANCY_CROSS_CUTTING_MATRIX.md) ·
test `tests/test_tenancy_table_classification.py`.

## Synthèse

| Clé | Valeur |
|---|---|
| START_SHA | `b40021ca91abf49f46da5bc762506b7786fd863e` (`origin/main` observé après `git fetch --all --prune`, identique à l'état annoncé) |
| END_SHA | dernier commit de la branche `foundation/tenant-architecture` (voir la PR ; un document ne peut pas contenir l'empreinte du commit qui le contient) |
| ACTUAL_SCHEMA_TABLE_COUNT | **49** (`Base.metadata`, tous modules `app/models/*` importés) + `alembic_version` |
| ALEMBIC_HEADS | **1** — `20260826_0043` |
| ARCHITECTURE_RECOMMENDATION | **D minimale** : base partagée + schéma partagé + `tenant_id` + RLS `FORCE` comme modèle unique du code ; silo par instance dédiée possible, même code, sans branche |
| TABLE_CLASSIFICATION_PERCENT | **100 %** (49/49 : 6 GLOBAL, 14 TENANT, 24 SITE, 0 UNIT, 2 TECHNICAL, 3 TBD documentés) — contrôlé par test |
| RLS_RECOMMENDATION | RLS `ENABLE` + `FORCE` sur toute table TENANT/SITE, politique `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` (absent ⇒ 0 ligne), `SET LOCAL` par transaction, rôle applicatif NOSUPERUSER NOBYPASSRLS non propriétaire, rôle de migration séparé. **Inopérante tant que P0-1 n'est pas levé.** |
| TENANT_CONTEXT_MODEL | `UserIdentity` → `TenantMembership` vérifié serveur → `TenantContext` immuable par requête ; `PlatformAdminContext` distinct, justifié, expirant. En-têtes/paramètres client = sélection, jamais autorisation. Manquant / invalide / non autorisé ⇒ DENY. Aucun fallback. |
| FIRST_VERTICAL_SLICE_RECOMMENDATION | **`exam_tariffs`** |

## État de départ affiché avant tout changement

```
CURRENT_MAIN_SHA          = b40021ca91abf49f46da5bc762506b7786fd863e
CURRENT_ALEMBIC_HEAD      = 20260826_0043
CURRENT_TABLE_COUNT       = 49
CURRENT_TENANCY_MECHANISM = aucun tenant ; filtre applicatif par chaîne libre `unit` (app/services/patient_access.py), fail-open
CURRENT_RLS_STATUS        = absente ; application connectée en superutilisateur propriétaire
```

## Choix du premier vertical slice

| Critère | `exam_tariffs` | `tat_targets` | `delta_check_rules` |
|---|---|---|---|
| Risque clinique | Aucun (prix) | Faible (indicateurs de délai) | **Clinique** (règles de delta-check) |
| Graphe relationnel | Aucune FK entrante/sortante ; lu par `tariff_service.get_price` (facturation, par `exam_code`) | Aucune FK ; lu par `tat_service` | Aucune FK ; lu par `delta_checker` |
| Comportement tenant représentatif | Oui : deux labos facturent le même code à des prix différents ; seed par tenant (`seed_tariffs`) | Oui | Oui |
| Test de contrainte unique | `UNIQUE(exam_code)` → `(tenant_id, exam_code)` : même code dans A et B accepté, doublon dans A refusé | Identique (`exam_code`) | `UNIQUE(analyte)` |
| Rollback | Trivial (colonne recalculable, pas d'enfants) | Trivial | Trivial |
| Données réelles requises | Non | Non | Non |
| Point d'attention | `get_price` doit recevoir le TenantContext : démontre la propagation dans un service appelé par un autre domaine (facturation) | Moins de chemins appelants | Toucher une règle clinique dès le premier slice est contraire au critère |

```
CANDIDATE_1           = exam_tariffs
CANDIDATE_2           = tat_targets
CANDIDATE_3           = delta_check_rules
RECOMMENDED_CANDIDATE = exam_tariffs
WHY                   = scope TENANT sans ambiguïté, zéro risque clinique, aucune FK,
                        une UNIQUE globale représentative à convertir, un seed à rendre
                        tenant-aware, et un consommateur inter-domaine (facturation)
                        qui prouve la propagation du TenantContext hors du router ;
                        rollback trivial, aucune donnée réelle nécessaire.
```

`exam_tariffs` existe toujours (`app/models/ruggylab_os.py`, endpoint
`app/api/v1/endpoints/tariffs.py`, service `app/services/tariff_service.py`) et son
scope métier est bien tenant-local (politique tarifaire d'une organisation).
**Non implémenté dans ce lot.**

## OPEN_P0

| ID | Constat | Preuve | Effet |
|---|---|---|---|
| P0-1 | L'application, le scheduler, le worker et Alembic se connectent avec `ruggylab` = `POSTGRES_USER` de l'image PostgreSQL, donc **superutilisateur propriétaire** | `docker-compose.yml` (`POSTGRES_USER`, `DATABASE_URL`), `.env.example:36` | Toute politique RLS, même `FORCE`, serait contournée. Bloque la démonstration d'isolation. |
| P0-2 | Aucun harness d'isolation A/B n'existe | absence de tests tenancy sur PostgreSQL | L'ADR reste une intention non démontrée → `READY_FOR_SCHEMA_EXPANSION = NO` |

## OPEN_P1

| ID | Constat |
|---|---|
| P1-ALEMBIC-METADATA | `alembic/env.py` utilise `app.db.base.Base.metadata`, qui n'enregistre que **46** tables : `aes_incidents`, `epi_notifications`, `reagent_lots` en sont absentes. Un `alembic revision --autogenerate` proposerait de les supprimer. Non corrigé ici (hors périmètre), à traiter avant toute migration de tenancy. |
| P1-UNIT-FAIL-OPEN | `patient_access.py` : `unit IS NULL` visible de tous et technicien sans unité transversal. Contraire au principe DENY par défaut (décision H6). |
| P1-DOC-DRIFT | `docs/ARCHITECTURE_AS_BUILT.md:31` annonce 44 tables (réel : 49). |
| P1-CACHE-PUBSUB | Clés de cache et canal pub/sub sans dimension tenant (matrice transverse). |
| P1-GLOBAL-UNIQUE | 14 contraintes UNIQUE métier globales à convertir (classification). |
| P1-ADMIN-SEMANTICS | `admin` n'est pas distingué d'un administrateur plate-forme. |

## RISKS

* Le terme « cloisonnement » dans le code et la documentation peut donner une
  fausse assurance d'isolation ; il désigne un filtre applicatif ouvert.
* Le mapping des chaînes libres `unit` vers `org_units` exige une validation
  humaine (variantes orthographiques) ; un mapping automatique créerait des
  fuites ou des pertes d'accès.
* Collision sémantique `unit` (organisation / mesure) : risque de jointure ou
  de migration sur la mauvaise colonne. Mitigé par le nommage `org_unit_id`.
* RLS ne couvre ni cache, ni fichiers, ni pub/sub, ni logs : ces canaux restent
  protégés par le seul code applicatif.
* Restauration d'un tenant non outillée : à construire avant le second tenant réel.

## HUMAN_DECISIONS_REQUIRED

H1 tenant fondateur · H2 identités multi-tenant · H3 référentiels cliniques
locaux ou communs (TBD-1, TBD-2) · H4 403 vs 404 · H5 tenant en silo ·
H6 suppression du pool `unit IS NULL` · TBD-3 connexion CSA par tenant.
Détails et propriétaires : ADR-001 §9 et classification §TBD.

## Contrôles exécutés

| Contrôle | Résultat |
|---|---|
| `git diff --check` | voir la PR (exécuté avant commit) |
| `pytest tests/test_tenancy_table_classification.py` | 5 passed |
| `ruff check` / `ruff format --check` sur le test ajouté | voir la PR |
| Type check | aucun type checker configuré dans `pyproject.toml` (non exécuté) |
| Tests existants | non modifiés |

```
ADR_MULTI_TENANCY = ACCEPTED_CANDIDATE
TABLE_CLASSIFICATION = 100%
READY_FOR_ISOLATION_HARNESS = YES
READY_FOR_SCHEMA_EXPANSION = NO
REAL_DATA_GO = NO
SITE_PRODUCTION_GO = NO
```
