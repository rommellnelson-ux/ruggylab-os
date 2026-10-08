# Gate FOUNDATION / ARCHITECTURE / MULTI-TENANCY — 2026-10-07

Programme RUGGYLAB-2027-READINESS. Lot d'architecture : **aucune migration,
aucun changement de code applicatif**. Livrables :
[ADR-001](../architecture/ADR-001-MULTI-TENANCY.md) ·
[Classification](../architecture/TENANCY_TABLE_CLASSIFICATION.md) ·
[Menaces](../architecture/TENANCY_THREAT_MODEL.md) ·
[Migration](../architecture/TENANCY_MIGRATION_PLAN.md) ·
[Matrice transverse](../architecture/TENANCY_CROSS_CUTTING_MATRIX.md) ·
test `tests/test_tenancy_table_classification.py`.

## Identification

```
START_SHA                     = b40021ca91abf49f46da5bc762506b7786fd863e
CURRENT_LOCAL_COMMIT          = 77d8a05 (premier commit du lot ; le commit de clôture suit, voir PR)
BRANCH                        = foundation/tenant-architecture

ACTUAL_SQLALCHEMY_TABLE_COUNT = 49
ALEMBIC_METADATA_TABLE_COUNT  = 46
ALEMBIC_HEAD_COUNT            = 1
ALEMBIC_HEAD                  = 20260826_0043

TENANT_TABLES                 = 14
SITE_TABLES                   = 24
UNIT_TABLES                   = 0
GLOBAL_TABLES                 = 6
TECHNICAL_TABLES              = 2
TBD_TABLES                    = 3
----------------------------------
TOTAL                         = 49  (= ACTUAL_SQLALCHEMY_TABLE_COUNT)

RLS_CURRENT                   = NONE
TENANT_ID_CURRENT             = NONE

SCHEMA_REGISTRATION_GAP       = OPEN
```

Les 3 TBD (`critical_ranges`, `reference_ranges`, `csa_sync_state`) ont chacun
raison, propriétaire de décision et question bloquante
([classification §TBD](../architecture/TENANCY_TABLE_CLASSIFICATION.md#tbd)) ; ils ne
sont pas forcés vers une classification artificielle.

## Synthèse

| Clé | Valeur |
|---|---|
| START_SHA | `b40021ca91abf49f46da5bc762506b7786fd863e` (`origin/main` observé après `git fetch --all --prune`, identique à l'état annoncé) |
| END_SHA | dernier commit de la branche `foundation/tenant-architecture` (voir la PR ; un document ne peut pas contenir l'empreinte du commit qui le contient) |
| ACTUAL_SCHEMA_TABLE_COUNT | **49** (`Base.metadata`, tous modules `app/models/*` importés) + `alembic_version` ; **46** seulement via `app.db.base` (chemin Alembic) |
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
| Risques | Régression de facturation si `get_price` ne reçoit pas le contexte (prix absent ⇒ facture fausse) ; seed `seed_tariffs` à rendre par tenant ; endpoint admin de tarifs à protéger contre l'écriture inter-tenant | Faible surface : moins de chemins appelants, donc démonstration moins probante ; dépend d'`exam_code` comme `exam_tariffs` | **Clinique** : une erreur de scope modifie silencieusement la détection de delta d'un autre laboratoire ; règle partagée ou locale non décidée (proche de TBD-1) |
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

## FOUNDATION_SCHEMA_REGISTRATION_GAP

```
FOUNDATION_SCHEMA_REGISTRATION_GAP = OPEN
SEVERITY = P0 before multi-tenant schema expansion
```

**FACT** — 49 tables SQLAlchemy sont présentes dans l'application (import de tous
les modules de `app/models/`).

**FACT** — Seulement 46 sont enregistrées dans le chemin de métadonnée utilisé par
Alembic (`alembic/env.py` → `target_metadata = app.db.base.Base.metadata`).
Absentes : `aes_incidents` (`app/models/aes.py`), `epi_notifications`
(`app/models/epi_notification.py`), `reagent_lots` (`app/models/reagent_lot.py`) —
aucun de ces modules n'est importé par `app/db/base.py`.

**IMPACT** — Une migration générée automatiquement (`alembic revision --autogenerate`,
`alembic check`) compare la base à une représentation incomplète du schéma :
elle peut ignorer ces 3 tables existantes ou proposer leur suppression.

**RISK** — Toute propagation `tenant_id`, politique RLS ou génération Alembic
appuyée sur cette métadonnée avant correction pourrait laisser ces tables (dont
`epi_notifications`, donnée de santé) hors migration, hors politique et hors isolation.

**RECOMMENDATION** — Lot de remédiation séparé, avant toute expansion générale du
schéma : enregistrer tous les modules de modèles dans `app/db/base.py` (ou
découverte automatique), puis `alembic check` sans diff sur une base à jour.

**THIS_LOT_ACTION** — Documentation only. No corrective code. Le constat est
verrouillé par deux tests : `test_l_ecart_de_metadonnee_alembic_est_exactement_celui_documente`
(l'écart est exactement ces 3 tables) et
`test_la_metadonnee_alembic_enregistre_toutes_les_tables` (`xfail strict` : il
passera au rouge en XPASS dès la remédiation, pour imposer la mise à jour de ce
rapport). Le test d'exhaustivité de la classification importe lui-même tous les
modules de modèles et n'est pas faussé par cet écart.

## OPEN_P0

| ID | Constat | Preuve | Effet |
|---|---|---|---|
| P0-1 | L'application, le scheduler, le worker et Alembic se connectent avec `ruggylab` = `POSTGRES_USER` de l'image PostgreSQL, donc **superutilisateur propriétaire** | `docker-compose.yml` (`POSTGRES_USER`, `DATABASE_URL`), `.env.example:36` | Toute politique RLS, même `FORCE`, serait contournée. Bloque la démonstration d'isolation. |
| P0-2 | Aucun harness d'isolation A/B n'existe | absence de tests tenancy sur PostgreSQL | L'ADR reste une intention non démontrée → `READY_FOR_SCHEMA_EXPANSION = NO` |
| P0-3 | **FOUNDATION_SCHEMA_REGISTRATION_GAP** : métadonnée Alembic 46/49 (voir section dédiée) | `alembic/env.py`, `app/db/base.py` ; tests du lot | P0 avant toute expansion multi-tenant du schéma |

## OPEN_P1

| ID | Constat |
|---|---|
| P1-UNIT-FAIL-OPEN | `patient_access.py` : `unit IS NULL` visible de tous et technicien sans unité transversal. Contraire au principe DENY par défaut (décision H6). |
| P1-WINDOWS-SSRF-TEST-HANG | `TestNotifyEndpointSsrfClosure` bloque indéfiniment sous Windows (patch global de `socket.socket`) ; préexistant ; la suite complète ne peut pas terminer sur poste Windows. Hors lot. |
| P1-DOC-DRIFT | `docs/ARCHITECTURE_AS_BUILT.md:31` annonce 44 tables (réel : 49). |
| P1-CACHE-PUBSUB | Clés de cache et canal pub/sub sans dimension tenant (matrice transverse). |
| P1-GLOBAL-UNIQUE | 14 contraintes UNIQUE métier globales à convertir (classification). |
| P1-ADMIN-SEMANTICS | `admin` n'est pas distingué d'un administrateur plate-forme. |

## OPEN_P2

| ID | Constat |
|---|---|
| P2-AGENTS-MD-TEST-DURATION | `AGENTS.md` annonce 2–3 min / ~478 tests ; la suite collecte 2499 tests (STALE). Documentation seulement. |

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

```
TYPE_CHECKER_CONFIGURED = YES   (mypy, [tool.mypy] dans pyproject.toml, cible `make lint` : mypy app)
TYPE_CHECK_RESULT       = PASS  (mypy app : Success: no issues found in 230 source files)
GIT_DIFF_CHECK          = PASS
RUFF_CHECK              = PASS  (tests/test_tenancy_table_classification.py, seul fichier Python modifié)
RUFF_FORMAT_CHECK       = PASS
LOT_CLASSIFICATION_TESTS= 8 passed, 1 xfailed (xfail strict documenté ci-dessous)
FULL_PYTEST_STATUS      = FAIL (1 échec PRE_EXISTING, 6 cas bloquants PRE_EXISTING+ENVIRONMENTAL ; aucune LOT_REGRESSION)
```

Campagne diagnostique (branche, Windows 11, Python 3.13.13) :
`pytest -vv --durations=50 -o faulthandler_timeout=300 -rfEsxX --deselect tests/test_stock_notifications.py::TestNotifyEndpointSsrfClosure`
(`pytest-timeout` absent de l'environnement, non installé ; la désélection est
explicite et uniquement due au blocage décrit plus bas — ce n'est pas un résultat vert pour ces cas).

```
FULL_PYTEST_STATUS = FAIL
COLLECTED = 2499 (main@b40021c : 2490 ; +9 = tests du lot)
TOTAL_RUN = 2493
PASSED    = 2474
FAILED    = 1
SKIPPED   = 17
XFAILED   = 1   (test_la_metadonnee_alembic_enregistre_toutes_les_tables, attendu)
XPASSED   = 0
DESELECTED= 7   (classe TestNotifyEndpointSsrfClosure : 6 cas paramétrés bloquants sous Windows + test_refusal_does_not_leak_the_internal_url, non exécuté donc non jugé)
DURATION  = 2372.15 s (39 min 32 s) ; mur 2401 s
```

| Échec | Reproduit sur main@b40021c | Cause | Classification |
|---|---|---|---|
| `tests/test_stock_predictor.py::TestHorizonPrediction::test_large_stock_saturates_rupture_date_at_date_max` — `date(8437, 9, 6) != date.max` | **Oui**, isolément (1 failed) | Probable : `cmm_seasonal` dépend du mois de la date de référence ; en octobre le facteur saisonnier ramène la rupture estimée sous `date.max`. Le test dépend de la date d'exécution ; la CI de `b40021c` était verte à la date du merge | **PRE_EXISTING** (test dépendant de la date ; non corrigé) |
| `TestNotifyEndpointSsrfClosure::test_internal_target_opens_no_socket[*]` (6) — blocage | **Oui** | voir « Diagnostic de durée » | **PRE_EXISTING + ENVIRONMENTAL** |

Tests du lot : 9 collectés — 8 passed, 1 xfailed. Aucun test existant modifié.

### Sémantique des deux tests de l'écart Alembic

* `test_l_ecart_de_metadonnee_alembic_est_exactement_celui_documente` — **défaut
  actuel attendu** : la métadonnée Alembic omet *exactement* `aes_incidents`,
  `epi_notifications`, `reagent_lots` (49 découvertes, 46 vues). Passe aujourd'hui ;
  devient rouge si l'écart passe à 0, 2, 4 tables ou change de composition.
* `test_la_metadonnee_alembic_enregistre_toutes_les_tables` — `xfail(strict=True)` :
  affirme l'état cible (aucune table manquante). Il échoue aujourd'hui (XFAIL) ;
  le jour de la remédiation il passe, et `strict` transforme ce XPASS en échec,
  ce qui oblige à retirer le marqueur et à mettre à jour ce rapport. Il ne peut
  pas masquer un écart de 2 ou 4 tables, puisque le test précédent échouerait alors.
* Le test d'exhaustivité de la classification importe tous les modules de
  `app/models/` et compare les 49 tables découvertes ; il n'est pas affecté par l'écart.

### Diagnostic de durée de la suite complète

```
EXPECTED_FULL_SUITE_DURATION = 2–3 min (AGENTS.md, « autour de 478 passed, 4 skipped »)
OBSERVED_COLLECTED           = 2499 items / 1 skipped (Windows 11, Python 3.13.13)
OBSERVED_FIRST_RUN           = démarrage 23:03:36 ; 92 % atteint vers 23:23:50 (2286 passed, 16 skipped, 0 failed) ; puis aucune progression
STATUS                       = ANOMALOUS (blocage), pas une lenteur générale
```

Constat corrigé : l'estimation intermédiaire « ~2 % après 20 min » était une
erreur de lecture du log ; la suite progressait normalement (~2 tests/s) jusqu'au blocage.

```
LAST_COMPLETED_TEST = tests/test_stock_notifications.py::TestStockNotificationEndpoint::test_notify_endpoint_high_stock_no_notifications
CURRENT_TEST        = tests/test_stock_notifications.py::TestNotifyEndpointSsrfClosure::test_internal_target_opens_no_socket[http://127.0.0.1/interne/admin]
ELAPSED_TIME        = ~70 min sur ce test (début ≈ 23:23:50, arrêt 00:34:18) ; suite totale ≈ 91 min
EXIT_REASON         = processus terminé par SIGTERM (EXIT=143) après diagnostic de deadlock ; vidage faulthandler à 120 s
```

**Cause** — le test fait `patch("app.utils.safe_http.socket.socket")`, ce qui
remplace l'attribut **global** `socket.socket` (le module est partagé). Le
`TestClient` Starlette démarre une boucle anyio/asyncio par portail ; sous
Windows, la boucle Proactor crée un `socketpair()` interne qui reçoit le mock ;
le thread de requête attend indéfiniment un futur (`anyio.from_thread.run_sync`
→ `concurrent.futures.result`) que la boucle ne servira jamais (pile faulthandler
archivée dans le log de diagnostic). Sous Linux (CI `ubuntu-latest`), la boucle
de sélecteur n'est pas affectée.

| Anomalie | Reproduit sur `origin/main@b40021c` | Code runtime modifié par le lot | Classification |
|---|---|---|---|
| Blocage `TestNotifyEndpointSsrfClosure` (6 cas paramétrés) sous Windows | **Oui**, à l'identique (faulthandler 60 s, même test, même pile) | Aucun | **PRE_EXISTING + ENVIRONMENTAL** (Windows) |
| Écart AGENTS.md (2–3 min / ~478 tests) vs 2499 tests | Oui (même collecte) | Aucun | **PRE_EXISTING** — `AGENTS_MD_TEST_DURATION_GUIDANCE = STALE` → P2 documentation |

`git diff b40021c...HEAD --stat` : 6 documents + `tests/test_tenancy_table_classification.py`,
**aucun fichier sous `app/`, `alembic/`, `scripts/`, ni dépendance modifiée**.
Aucune anomalie préexistante n'est corrigée dans ce lot. `AGENTS.md` n'est pas modifié.

### Tests lents (branche, `--durations=50`)

```
TESTS > 30s = 1
TESTS > 5s  = 46 (dont ~35 en phase setup ≈ 5–7 s : fixture applicative par test sous Windows)
TESTS apparently hanging = 6 (TestNotifyEndpointSsrfClosure, Windows)
```

| Durée | Phase | Test |
|---|---|---|
| 169.26 s | call | test_g0_security_baseline.py::test_the_gate_covers_the_whole_tracked_tree |
| 27.34 s | call | test_alembic_migrations.py::test_migrations_downgrade_base |
| 26.35 s | call | test_g0_security_baseline.py::test_two_generations_produce_the_same_payload |
| 23.76 s | call | test_alembic_migrations.py::test_migrations_idempotent_roundtrip |
| 16.94 s | call | test_g0_security_baseline.py::test_check_passes_on_the_versioned_artifacts |
| 16.65 s | call | test_g0_security_baseline.py::test_the_secret_probes_are_not_vacuous |
| 14.59 s | setup | test_g0_security_baseline.py::test_the_versioned_artifacts_match_a_fresh_build |
| 14.42 s | call | test_alembic_migrations.py::test_equipment_registry_migration_preserves_existing_rows |
| 14.23 s | call | test_g0_security_baseline.py::test_check_detects_a_softened_qualification |
| 13.56 s | call | test_g0_security_baseline.py::test_check_detects_a_divergence |
| 10.78 s | call | test_alembic_migrations.py::test_migrations_upgrade_head[None] |
| 7.14 s | setup | test_token_revocation.py::TestRevokedTokenRejectedOnWebSocket::test_revoked_token_cannot_open_ws |
| 6.58 s | call | test_g0_inventory.py::test_two_generations_produce_the_same_payload |
| 6.56 s | setup | test_security_hardening.py::TestAmendRbac::test_technician_cannot_amend |
| 6.30 s | call | test_g0_quality_baseline.py::test_ajouter_une_preuve_acceptee_ne_deplace_aucune_empreinte_de_mesure |
| 6.20 s | setup | test_bnpl_tracker.py::TestGetOverdue::test_multiple_overdue_plans |
| 6.18 s | setup | test_quality_nc_capa.py::TestNonConformityWorkflow::test_valid_transition_sequence |
| 6.16 s | setup | test_results_poct_batch.py::test_no_critical_threshold_is_applied_before_qualification |
| 6.14 s | setup | test_report_delivery_outbox.py::test_patient_portal_channel_writes_snapshot_pdf |
| 6.13 s | setup | test_imaging_transaction_safety.py::test_imaging_reservation_rolls_back_when_audit_fails |
| 6.10 s | setup | test_invoices.py::TestInvoiceCmuMath::test_insured_requires_insurance_id |
| 6.04 s | setup | test_preanalytic_cancelled_sample_safety.py::test_cancelled_sample_rejects_standard_result_before_stock_or_audit |
| 5.96 s | setup | test_results_rbac.py::TestResultsUnitScope::test_cockpit_excludes_other_unit |
| 5.95 s | setup | test_rbac_and_compliance_trend.py::TestComplianceTrend::test_compliance_html_report |
| 5.91 s | setup | test_token_revocation.py::TestAccessTokenHasJti::test_token_decodes_with_jti |
| 5.85 s | setup | test_rbac_and_compliance_trend.py::TestPatientRbacScoping::test_denied_access_is_audited |
| 5.82 s | setup | test_registre_import_analytics.py::TestRegistreImport::test_import_requires_officer |
| 5.76 s | setup | test_sample_aspect.py::TestSampleAspectApi::test_invalid_aspect_rejected |
| 5.75 s | setup | test_invoices.py::TestInvoiceRbac::test_technician_denied |
| 5.65 s | setup | test_qc.py::TestQcApi::test_deactivate_unknown_control_returns_404 |

Aucun de ces tests ne touche un fichier du lot. La durée totale (~40 min sur ce
poste) contre 2–3 min annoncées s'explique par le volume (2499 vs ~478 tests) et
un coût de setup de ~5 s par test API sous Windows : `AGENTS_MD_TEST_DURATION_GUIDANCE = STALE` (P2).

## Décisions structurantes

1. Modèle unique du code : shared database + shared schema + `tenant_id` + RLS `FORCE` ; silo = instance dédiée, même code.
2. TENANT est la seule frontière dure ; SITE et UNIT (`org_units`) sont des frontières d'autorisation internes.
3. Source de vérité du contexte : `TenantMembership` vérifiée serveur ; jamais un identifiant fourni par le client ; aucun fallback.
4. Prérequis avant toute migration tenant : P0-1 (rôles BD), P0-2 (harness A/B), P0-3 (registre de métadonnée).
5. Premier vertical slice : `exam_tariffs` (non implémenté).

```
ADR_MULTI_TENANCY = ACCEPTED_CANDIDATE
TABLE_CLASSIFICATION = 100%
READY_FOR_ISOLATION_HARNESS = YES
READY_FOR_SCHEMA_EXPANSION = NO

FOUNDATION_SCHEMA_REGISTRATION_GAP = OPEN
REAL_DATA_GO = NO
SITE_PRODUCTION_GO = NO
```
