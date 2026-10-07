# ADR-001 — Modèle multi-tenant de RuggyLab OS

| Champ | Valeur |
|---|---|
| Statut | **ACCEPTED_CANDIDATE** (proposé, en attente des décisions humaines listées en §9) |
| Date | 2026-10-07 |
| Programme | RUGGYLAB-2027-READINESS — phase FOUNDATION / ARCHITECTURE / MULTI-TENANCY |
| Base observée | `origin/main` = `b40021ca91abf49f46da5bc762506b7786fd863e` |
| Documents liés | [TENANCY_TABLE_CLASSIFICATION](TENANCY_TABLE_CLASSIFICATION.md) · [TENANCY_THREAT_MODEL](TENANCY_THREAT_MODEL.md) · [TENANCY_MIGRATION_PLAN](TENANCY_MIGRATION_PLAN.md) · [TENANCY_CROSS_CUTTING_MATRIX](TENANCY_CROSS_CUTTING_MATRIX.md) |

Cet ADR ne modifie aucun code applicatif ni aucun schéma. Il fixe la cible et les
invariants que les lots suivants devront respecter.

---

## 1. Inventaire as-built (établi depuis le code, pas depuis la documentation)

Méthode : import de `app.db.base.Base` et de tous les modules de `app/models/`,
lecture de `Base.metadata.tables`, `python -m alembic heads`, lecture de
`app/services/patient_access.py`, `app/models/ruggylab_os.py`, `app/api/deps.py`,
`app/core/cache_decorator.py`, `app/services/redis_notification.py`,
`app/scheduler.py`, `docker-compose.yml`, `.env.example`, `alembic/versions/`.

| Fait | Valeur observée |
|---|---|
| Nombre de tables (métadonnée SQLAlchemy) | **49** (+ `alembic_version`, technique Alembic) |
| Alembic heads | **1** — `20260826_0043` |
| Colonne `tenant_id` / `organization_id` dans le schéma | **Absente** (les seules occurrences de `tenant_id` sont dans `app/core/secrets_manager.py` et désignent le tenant **Azure AD**, sans rapport avec la donnée) |
| PostgreSQL RLS | **Absente** (aucun `ENABLE ROW LEVEL SECURITY`, `CREATE POLICY`, `set_config`, `current_setting` dans `app/` ou `alembic/`) |
| Rôle PostgreSQL applicatif | `ruggylab` = `POSTGRES_USER` de l'image officielle → **superutilisateur et propriétaire des tables**. Le même rôle exécute l'application, le scheduler, le worker et les migrations Alembic. |
| Modèle utilisateur | `users(id, username UNIQUE global, role, unit, auth_version, …)` — **un rôle unique et une unité unique par utilisateur**, portés directement par la ligne `users` |
| Rôles | `UserRole` = `technician`, `officer`, `admin`, `accountant` (enum applicatif, pas de rôle plate-forme distinct) |
| Mécanisme de cloisonnement actuel | **Applicatif uniquement**, par chaîne libre `unit` (`String(100)`) : `app/services/patient_access.py` (`can_access_*`, `apply_*_scope`) utilisé par 10 endpoints et 6 services |
| Sémantique du cloisonnement | `admin`/`officer` → tout ; `technician` **sans unité → tout** ; technicien avec unité → sa propre unité **+ toutes les lignes `unit IS NULL`** (« pool partagé ») ; résultat/échantillon sans patient → autorisé |
| Cache | Clé = chemin + méthode + query + `user_id` (`cache_decorator.py`) — **pas de dimension tenant** |
| Pub/Sub | Un canal Valkey unique `NOTIF_CHANNEL` pour toute l'instance (`redis_notification.py`) |
| WebSocket | `/notifications` — push périodique filtré par périmètre utilisateur |
| Jobs de fond | `scheduler.py` : nettoyage des jetons (global), synchro CSA (singleton `csa_sync_state`) ; outbox de diffusion des rapports ; jobs paludisme |
| Fichiers | Répertoire local unique `MICROSCOPY_STORAGE_DIR = data/microscopy`, colonnes `image_url` / `storage_reference` sans préfixe d'organisation |

### Écarts documentation ↔ code

| FACT | DOCUMENTED_STATE | ACTUAL_STATE | DELTA |
|---|---|---|---|
| Nombre de tables | `docs/ARCHITECTURE_AS_BUILT.md:31` : « app/models (44 tables) » | 49 | **+5 — document historique périmé.** `docs/g0/INVENTORY.md`, `SCHEMA.md`, `C4.md` indiquent bien 49 : aligné. |
| Alembic head | `docs/g0/DEPLOYMENT_CSA_GR_PLATEAU.md:91` : `20260826_0043` | `20260826_0043` | Aucun |
| Cloisonnement | Docstring `patient_access.py` : « Cloisonnement RBAC … par unité / service » | Cloisonnement **ouvert par défaut** (`unit IS NULL` = visible de tous, technicien sans unité = transversal) | Le terme « cloisonnement » surestime la garantie : c'est un filtre de confort, pas une isolation. **Non conforme au principe « missing context → DENY » visé.** |
| Rôle BD | `.env.example` / `docker-compose.yml` : un seul utilisateur `ruggylab` | Superutilisateur propriétaire | Aucun document ne décrit de séparation rôle applicatif / rôle de migration. **Bloquant pour RLS** (un superutilisateur contourne RLS, même `FORCE`). |

---

## 2. Contexte et contraintes

* Le produit est aujourd'hui **mono-organisation** : une instance = un laboratoire
  (HIA / plateau CSA). Le seul découpage interne est l'« unité » militaire/service,
  en chaîne libre.
* La cible 2027 impose de servir plusieurs organisations (tenants), chacune
  pouvant posséder plusieurs sites, chacun contenant plusieurs unités.
* Données de santé : une fuite inter-tenant est un incident de sécurité majeur
  (secret médical, RGPD art. 9, réglementation locale).
* Équipe d'exploitation réduite ; sites pouvant fonctionner en conditions
  dégradées. Le coût opérationnel compte autant que l'isolation.
* Schéma existant : 49 tables, nombreuses contraintes `UNIQUE` globales
  (`patients.ipp_unique_id`, `samples.barcode`, `invoices.invoice_number`,
  `exam_tariffs.exam_code`, `users.username`, …).

---

## 3. Options comparées

* **A** — base partagée, schéma partagé, discriminant `tenant_id` sur chaque table métier.
* **B** — base partagée, **un schéma PostgreSQL par tenant**.
* **C** — **une base (ou un cluster) par tenant**.
* **D** — hybride : A par défaut, C (« silo ») pour un tenant qui l'exige
  contractuellement ou réglementairement, avec le **même code et le même schéma**.

Échelle : ++ très favorable · + favorable · 0 neutre · − défavorable · −− très défavorable.

| Critère | A shared schema | B schema/tenant | C DB/tenant | D hybride (A + silo C) |
|---|---|---|---|---|
| Security isolation | − seule, **+ avec RLS FORCE + rôle non-propriétaire** | + (`search_path`), mais une erreur de `search_path` suffit à fuiter | ++ physique | + (A durci pour le pool, ++ pour les silos) |
| PostgreSQL RLS | ++ conçu pour ce cas | 0 inutile / redondant | 0 inutile | ++ dans le pool, sans objet dans les silos |
| Migrations | ++ une seule exécution Alembic | −− N exécutions, dérive de schéma, Alembic non natif multi-schéma | −− N bases à migrer, orchestrations partielles | + une version de schéma, N_silo petites exécutions |
| Unique constraints | − toutes à réécrire en `(tenant_id, …)` | ++ inchangées | ++ inchangées | − comme A |
| Foreign keys | − FK composites `(tenant_id, id)` nécessaires pour empêcher les références croisées | ++ naturelles | ++ naturelles | − comme A |
| Transactions | ++ normales | + normales (intra-schéma) | + normales, mais aucune transaction plate-forme | + |
| Performance | + index préfixés `tenant_id`, partitionnement possible plus tard ; risque « voisin bruyant » | − catalogue PostgreSQL qui gonfle (49 tables × N), cache de plans | + isolée, mais pools de connexions × N | + |
| Operations | ++ un cluster | − N schémas à surveiller | −− N clusters | + quelques silos seulement |
| Background jobs | + un worker, contexte tenant **explicite par job** | − worker doit itérer sur les schémas | −− un worker ou une config par base | + |
| Valkey / cache | − préfixe tenant obligatoire dans chaque clé | − idem | + instance par tenant possible | − comme A |
| Files / storage | − préfixe `tenant/` obligatoire | − idem | + bucket par tenant | − comme A |
| Audit | + une table, `tenant_id` obligatoire | − audit éclaté | − audit éclaté, vue plate-forme impossible sans ETL | + |
| Exports / reporting | + agrégats plate-forme faciles (et donc **dangereux** : à garder en contexte plate-forme explicite) | − UNION sur N schémas | −− ETL | + |
| Backup | + un seul | 0 un seul, mais restauration fine délicate | ++ par tenant | + |
| Restore of one tenant | −− extraction logique filtrée (`COPY … WHERE tenant_id`) à outiller et tester | + `pg_dump -n` | ++ trivial | − pool : comme A ; silo : ++ |
| PRA | + un plan | + | − N plans | + |
| Observability | + labels `tenant` à ajouter (cardinalité maîtrisée) | 0 | − N cibles | + |
| Cross-tenant administration | + possible, **doit** passer par `PlatformAdminContext` audité | 0 | −− | + |
| SaaS scalability | ++ jusqu'à des centaines de tenants | − limite pratique ~dizaines | −− coût linéaire | ++ |
| Operational cost | ++ | − | −− | + |
| Migration from current architecture | + ajout de colonnes et backfill vers un tenant unique « fondateur » | −− déplacer toutes les tables dans un schéma et reconfigurer `search_path` partout | −− déploiement par tenant, inexistant aujourd'hui | + identique à A au départ |

### Lecture

* **B** cumule les inconvénients : isolation qui repose sur un `search_path`
  (contournable par une seule requête qualifiée ou un pool mal réinitialisé),
  Alembic à exécuter N fois, catalogue qui grossit. Écarté.
* **C** offre la meilleure isolation mais multiplie le coût d'exploitation,
  rend l'audit et l'administration plate-forme impossibles sans ETL et ne
  correspond à aucune capacité de déploiement actuelle. À garder comme mode
  d'exception.
* **A** est la seule option compatible avec une équipe réduite et une seule
  chaîne de migration, **à condition** que l'isolation ne dépende pas que du
  code applicatif : RLS en `FORCE`, rôle applicatif non-propriétaire, FK
  composites, clés de cache et chemins de fichiers préfixés.

---

## 4. Décision (recommandation unique)

> **Option D, dans sa forme minimale : architecture A (base partagée, schéma
> partagé, discriminant `tenant_id` + PostgreSQL RLS `FORCE` en défense en
> profondeur) comme modèle unique du code ; possibilité contractuelle de
> déployer un tenant dans une instance dédiée (« silo ») en exécutant
> exactement le même code et le même schéma, sans aucune branche de code
> spécifique.**

Conséquences : pour le code et le schéma, **on implémente A**. Le silo n'est
qu'un choix de déploiement (une instance contenant un seul tenant) ; il ne crée
aucun chemin de code. Aucune fonctionnalité ne doit supposer « un seul tenant
par base ».

Conditions non négociables pour que A soit acceptable (voir §6) :

1. `tenant_id NOT NULL` sur toute table de scope TENANT / SITE / UNIT, à terme.
2. RLS `ENABLE` + `FORCE` sur ces tables, politiques fondées sur un paramètre
   de session transactionnel, **refus si le paramètre est absent**.
3. L'application se connecte avec un rôle **non superutilisateur, non
   propriétaire, sans `BYPASSRLS`**. Les migrations utilisent un rôle distinct.
4. FK composites `(tenant_id, parent_id) → parent(tenant_id, id)` pour toute
   relation intra-tenant.
5. Toute clé Valkey, tout canal pub/sub, tout chemin de fichier, tout label de
   log/metric relatif à une donnée métier est préfixé par le tenant.
6. Aucun fallback vers un tenant par défaut, nulle part.

---

## 5. Modèle conceptuel

```
PLATFORM                         (l'instance RuggyLab OS ; opérée par l'éditeur/exploitant)
 └── TENANT / ORGANIZATION       (entité juridique ou administrative cliente ; frontière d'isolation)
      ├── SITE A                 (lieu physique : laboratoire, HIA, antenne, plateau CSA)
      │    ├── UNIT 1            (service/formation rattachée : périmètre organisationnel d'accès)
      │    └── UNIT 2
      └── SITE B
           └── UNIT 3

USER (UserIdentity, global à la plate-forme)
 └── TenantMembership (user × tenant, rôle(s), sites/unités autorisés)

PLATFORM_ADMIN : capacité séparée, jamais déduite d'un rôle de tenant.
```

| Concept | Définition | Frontière de sécurité ? | Table cible (future) |
|---|---|---|---|
| PLATFORM | L'instance et son exploitant | — | aucune (configuration) |
| TENANT / ORGANIZATION | Client contractuel ; propriétaire des données ; unité de restauration, d'export et de facturation | **Oui — frontière dure (RLS)** | `tenants` |
| SITE | Lieu physique où se trouvent analyseurs, stocks, échantillons | Non dure : filtre d'autorisation à l'intérieur du tenant | `sites (tenant_id, …)` |
| UNIT | Unité organisationnelle (service, formation militaire) rattachée à un site | Non dure : filtre d'autorisation | `org_units (tenant_id, site_id, …)` |
| USER | Identité authentifiable, unique sur la plate-forme | — | `users` (sans rôle ni unité à terme) |
| ROLE | Ensemble de permissions **à l'intérieur d'un tenant** | — | porté par `tenant_memberships` |
| PLATFORM_ADMIN | Exploitant plate-forme ; aucun accès implicite aux données de santé | Contexte distinct, audité, à durée limitée | `platform_admins` ou claim dédié |

### Interdits explicites

* `TENANT == SITE`, `TENANT == UNIT`, `ORGANIZATION == SITE` : **jamais**
  encodés implicitement (pas de « un site = un tenant » dans le code, pas de
  réutilisation de `military_facilities` comme table de tenants).
* Le rôle `admin` actuel est un **administrateur de tenant**, pas un
  administrateur plate-forme.

### Collisions sémantiques identifiées

| Terme | Sens 1 | Sens 2 | Occurrences | Décision |
|---|---|---|---|---|
| `unit` | Unité **organisationnelle** (chaîne libre) | Unité **de mesure** (g/L, mmol/L, « unit ») | Organisationnelle : `users.unit`, `patients.unit`, `equipments.unit`. Mesure : `reagents.unit`, `equipment_approved_analytes.unit`, `ratio_preset_items.reagent_unit`, `biological_code_mappings.unit`, `biological_reference_ranges.unit`, `critical_ranges.unit`, `delta_check_rules.unit`, `qc_controls.unit`, `reference_ranges.unit`. Prix : `invoice_lines.unit_price_xof` | La nouvelle entité s'appelle **`org_units`** et la FK **`org_unit_id`**. Les colonnes de mesure ne sont pas renommées dans ce programme ; toute nouvelle colonne de mesure s'appelle `measurement_unit` / `ucum_unit`. Interdiction de créer une colonne nommée `unit_id`. |
| `tenant_id` | Tenant RuggyLab | Tenant **Azure AD** (`app/core/secrets_manager.py`, `AZURE_TENANT_ID`) | 1 module | Renommer la variable locale en `azure_tenant_id` lors d'un lot ultérieur ; d'ici là, la classification et le test de garde ignorent `app/core/secrets_manager.py`. |
| `location` / `division` / `region` | Lieu physique | Découpage militaire (`military_facilities`) | `equipments.location`, `aes_incidents.location`, `military_facilities.*` | `military_facilities` reste un **référentiel GLOBAL** ; un SITE peut y faire référence, ce n'est pas un SITE. |
| `requesting_service` | Service demandeur (texte) | UNIT | `exam_orders.requesting_service` | Rester texte libre ; ne pas en déduire une UNIT. |

---

## 6. Tenant context

### Source de vérité

Le tenant d'une requête **n'est jamais une donnée fournie par le client qui
vaudrait autorisation**. `tenant_id`, `X-Tenant-ID`, `organization_id`, un
paramètre de chemin ou de requête sont au mieux une **sélection** parmi les
tenants auxquels l'identité authentifiée appartient, jamais une preuve.

```
UserIdentity        = utilisateur authentifié (JWT vérifié, auth_version à jour, actif)
TenantMembership    = (user_id, tenant_id, roles[], site_ids[]|ALL, org_unit_ids[]|ALL, status, valid_from, valid_to)
TenantContext       = (tenant_id, membership_id, roles, allowed_site_ids, allowed_org_unit_ids, request_id)
                      — construit côté serveur, immuable pour la durée de la requête
PlatformAdminContext= (platform_admin_id, justification, ticket_ref, expires_at, target_tenant_id|None)
                      — jamais construit implicitement ; jamais combiné à un TenantContext ordinaire
```

### Résolution

1. Authentifier → `UserIdentity`.
2. Lire le tenant demandé (claim `tid` d'un jeton émis après sélection, ou
   en-tête de sélection) **uniquement comme candidat**.
3. Charger la `TenantMembership` active (user, tenant candidat). Absente,
   suspendue ou expirée → **403**, journalisé.
4. Construire le `TenantContext` et l'injecter (dépendance FastAPI) ; ouvrir la
   transaction et exécuter `SELECT set_config('app.tenant_id', :tid, true)`
   (portée **transactionnelle**, `SET LOCAL`).

| Situation | Comportement |
|---|---|
| Contexte tenant manquant | **DENY** (403 côté API, zéro ligne + erreur côté BD) |
| Contexte tenant invalide (UUID mal formé, tenant inconnu ou désactivé) | **DENY** |
| Tenant non autorisé pour l'identité | **DENY** (403, pas 404 différencié, pour limiter l'énumération — à trancher en §9) |
| Utilisateur à un seul membership | Sélection **explicite** encore requise dans le jeton ; pas d'auto-sélection silencieuse côté BD |
| Aucun membership | Authentification possible, aucune route métier accessible |

**Aucun fallback** vers un tenant par défaut, ni dans l'application, ni dans
les politiques RLS (`current_setting('app.tenant_id', true)` NULL ⇒ prédicat
faux), ni dans les jobs.

---

## 7. PostgreSQL RLS (défense en profondeur)

### Rôles

| Rôle | Attributs | Usage |
|---|---|---|
| `ruggylab_owner` | `NOLOGIN`, propriétaire des objets | possède le schéma |
| `ruggylab_migrator` | `LOGIN`, membre de `ruggylab_owner`, utilisé **uniquement** par Alembic | DDL, backfills |
| `ruggylab_app` | `LOGIN`, **NOSUPERUSER NOBYPASSRLS**, non propriétaire, `GRANT SELECT/INSERT/UPDATE/DELETE` | API, worker, scheduler |
| `ruggylab_platform_ops` | `LOGIN`, `NOBYPASSRLS`, politiques dédiées lisant `app.platform_admin` | administration plate-forme auditée |
| `ruggylab_backup` | `BYPASSRLS` ou superutilisateur, hors application | `pg_dump` complet, PRA |

Constat actuel : l'application tourne en superutilisateur propriétaire.
**Tant que ce n'est pas corrigé, RLS n'apporte aucune garantie** (P0, voir rapport de gate).

### Politique type (table de scope TENANT)

```sql
ALTER TABLE exam_tariffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE exam_tariffs FORCE  ROW LEVEL SECURITY;   -- s'applique aussi au propriétaire

CREATE POLICY tenant_isolation ON exam_tariffs
  USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

* Paramètre absent ou vide ⇒ `NULLIF(...)` = NULL ⇒ prédicat NULL ⇒ **aucune
  ligne visible, aucune écriture possible**. Valeur non-UUID ⇒ erreur de cast
  ⇒ transaction en échec. Les deux sont des refus.
* Propagation : `set_config('app.tenant_id', …, is_local => true)` au début de
  chaque transaction, dans la dépendance de session. Jamais `SET` de session
  (fuite via le pool). Un listener `after_begin` SQLAlchemy vérifie qu'un
  contexte a été posé et lève sinon.
* SITE/UNIT ne sont **pas** des politiques RLS au départ (filtres applicatifs
  dans le tenant) ; on pourra ajouter une politique site plus tard pour les
  tables les plus sensibles.
* Migrations : `ruggylab_migrator` est membre du propriétaire ; avec `FORCE`,
  il est soumis aux politiques. Les backfills posent explicitement
  `app.tenant_id` par lot, ou utilisent une politique de migration dédiée
  activée seulement pendant la fenêtre.

### Workers et jobs

Chaque job porte un `tenant_id` explicite dans sa charge utile ; le worker ouvre
une transaction par tenant et pose `app.tenant_id`. Les jobs réellement
plate-forme (nettoyage des jetons) n'accèdent qu'à des tables TECHNICAL/GLOBAL
non soumises à RLS. Un job sans tenant qui touche une table tenantisée échoue
(zéro ligne, assertion).

### Test d'acceptation exigé (harness d'isolation, lot suivant)

« Le développeur oublie le filtre » : sur PostgreSQL réel, avec le rôle
`ruggylab_app`, créer des lignes pour les tenants A et B, poser
`app.tenant_id = A`, exécuter `SELECT * FROM exam_tariffs` **sans** clause
`WHERE tenant_id` → seules les lignes de A reviennent ; `UPDATE exam_tariffs SET
price_xof = 0` → n'affecte que A ; `INSERT … tenant_id = B` → refusé par
`WITH CHECK` ; sans `app.tenant_id` → zéro ligne. Le même test, exécuté en
superutilisateur, doit être **marqué comme démontrant le contournement** afin
de prouver que le rôle a de l'importance.

---

## 8. Conséquences

Positives : une seule chaîne de migration ; isolation vérifiable par la base ;
modèle conforme à la cible Tenant → Site → Unit ; administration plate-forme
possible et auditée.

Négatives / coûts : réécriture de toutes les `UNIQUE` métier ; FK composites ;
outillage de restauration d'un seul tenant à construire ; discipline sur les
clés de cache, chemins de fichiers et labels ; refonte du modèle
`users.role`/`users.unit` vers `tenant_memberships`.

Risques résiduels : contournement par un rôle privilégié (sauvegarde, migrateur) ;
erreurs dans les politiques ; fuites par canaux non-SQL (cache, fichiers,
logs) que RLS ne couvre pas — traités dans le modèle de menaces.

---

## 9. Décisions humaines requises avant `ACCEPTED`

| # | Question | Propriétaire proposé |
|---|---|---|
| H1 | Qui est le premier tenant (« tenant fondateur ») auquel seront rattachées toutes les données existantes ? Une instance actuelle = un tenant ? | Direction programme / DSI SSA |
| H2 | Les identités utilisateurs peuvent-elles appartenir à plusieurs tenants (personnel détaché) ? | RSSI + RH métier |
| H3 | Les référentiels cliniques (`reference_ranges`, `critical_ranges`) sont-ils propres à chaque laboratoire ou communs ? | Biologiste responsable / qualité |
| H4 | Accès hors périmètre : 403 ou 404 ? | RSSI |
| H5 | Existe-t-il un tenant contractuellement tenu à un silo (option C) ? | Direction / juridique |
| H6 | Le « pool partagé » `unit IS NULL` doit-il disparaître (recommandé) ? | Biologiste responsable + RSSI |
