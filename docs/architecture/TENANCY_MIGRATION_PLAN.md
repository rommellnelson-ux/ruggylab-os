# Plan de migration multi-tenant

Référence : [ADR-001](ADR-001-MULTI-TENANCY.md), [classification](TENANCY_TABLE_CLASSIFICATION.md).
Base : `b40021c`, head Alembic `20260826_0043`, 49 tables.

**Ce lot ne crée aucune migration.** Ce document fixe la séquence ; chaque étape
est un lot distinct, réversible, précédé de sa propre revue.

Principe directeur : **expand → backfill → verify → contract**, table par table
(ou graphe de tables fortement liées), jamais « tout le schéma d'un coup ».

## Étape 0 — Prérequis (bloquants)

| # | Action | Sortie vérifiable |
|---|---|---|
| 0.1 | Corriger l'enregistrement de la métadonnée Alembic (P0-3 FOUNDATION_SCHEMA_REGISTRATION_GAP : `aes_incidents`, `epi_notifications`, `reagent_lots` absents de `app.db.base`) | `alembic check` sans diff sur base à jour |
| 0.2 | Séparer les rôles PostgreSQL : `ruggylab_owner` / `ruggylab_migrator` / `ruggylab_app` (NOSUPERUSER NOBYPASSRLS) ; l'application cesse d'utiliser le superutilisateur | Test : `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user` → `f, f` au démarrage de l'API |
| 0.3 | Harness d'isolation A/B (PostgreSQL réel, deux tenants jetables) | Tests T01–T04, T16–T18 exécutables, rouges tant que rien n'est tenantisé |
| 0.4 | Décisions humaines H1, H2, H4 de l'ADR | Consignées dans l'ADR → statut ACCEPTED |

## Étape 1 — Tables d'organisation (expand pur, additif)

Créer `tenants`, `sites`, `org_units`, `tenant_memberships` (+ `platform_audit_events`).
Aucune table existante modifiée. Insérer **un tenant fondateur** (H1), ses sites
et ses unités à partir des valeurs distinctes de `users.unit`, `patients.unit`,
`equipments.unit` — **mapping validé par un humain**, jamais déduit
automatiquement (les chaînes libres contiennent des variantes orthographiques).
Créer un membership par utilisateur existant, rôle recopié.
Rollback : `DROP` des nouvelles tables (aucune donnée existante touchée).

## Étape 2 — Vertical slice (`exam_tariffs`, voir rapport de gate)

Démontrer le cycle complet sur une seule table non clinique avant toute extension.

## Étape 3+ — Extension par graphe, du moins au plus sensible

Ordre proposé : référentiels TENANT non cliniques (`tat_targets`, `notif_configs`)
→ qualité (`non_conformities`, `corrective_actions`) → équipements et stocks
(graphe `equipments` …) → facturation (`invoices` …) → clinique
(`patients`, `samples`, `results`, `exam_orders`, rapports) → `audit_events` en dernier.
La migration patient/résultat/facture est **explicitement hors de ce programme de lot**.

## Réponses aux questions imposées

### Comment attribuer un tenant aux données existantes ?

Toutes les lignes existantes appartiennent à l'unique organisation de
l'instance : backfill `UPDATE … SET tenant_id = :tenant_fondateur` par lots
(`WHERE tenant_id IS NULL AND id BETWEEN …`), idempotent. `site_id` : site unique
du tenant fondateur si l'instance n'en a qu'un ; sinon dérivé d'un parent
déjà sité (échantillon → résultat) ou d'un mapping validé. Une instance hébergeant
déjà, de fait, plusieurs organisations n'est **pas** prise en charge par ce
backfill : elle exige un mapping explicite par ligne (ticket dédié).

### Comment éviter les lignes orphelines ?

1. Avant backfill : requêtes de détection d'orphelins par FK existante
   (`LEFT JOIN parent … WHERE parent.id IS NULL`) — résultat attendu 0, sinon arrêt.
2. Backfill des enfants **depuis le parent** (`UPDATE child SET tenant_id = p.tenant_id FROM parent p …`),
   pas depuis la constante, pour que la cohérence parent/enfant soit structurelle.
3. Contrôle post-backfill : `COUNT(*) WHERE tenant_id IS NULL` = 0 et
   `COUNT(*) child JOIN parent ON … WHERE child.tenant_id <> parent.tenant_id` = 0.
4. Références textuelles sans FK (`bnpl_schedules.patient_ref`,
   `non_conformities.linked_entity_id`, `dh36_inbound_messages.sample_barcode`)
   : rapport d'anomalies manuel avant contraction.

### À quel moment rendre `tenant_id` NOT NULL ?

Après : backfill terminé, contrôles à 0, **et** code applicatif écrivant
systématiquement `tenant_id` déployé et observé (au moins un cycle complet
d'exploitation). Méthode sans verrou long : `ADD CONSTRAINT … CHECK (tenant_id IS NOT NULL) NOT VALID`,
puis `VALIDATE CONSTRAINT`, puis `SET NOT NULL` (PostgreSQL utilise la contrainte
validée pour éviter le scan), puis suppression du CHECK.

### À quel moment activer RLS ?

Par table, **après** NOT NULL et **après** que toutes les sessions
applicatives posent `app.tenant_id` (vérifié par le listener). Séquence :
politique créée → `ENABLE` → `FORCE` dans la même migration, sur une table à la
fois, avec le test « filtre oublié » de cette table au vert en CI PostgreSQL.
Jamais avant l'étape 0.2 (sinon RLS est inopérante en superutilisateur).

### Comment migrer les UNIQUE globales ?

1. Créer l'index composite `UNIQUE (tenant_id, col)` `CONCURRENTLY` (hors transaction Alembic, `autocommit_block`).
2. Basculer le code (`ON CONFLICT`, lookups) sur la paire.
3. Supprimer l'ancienne contrainte globale — uniquement quand le second tenant
   est sur le point d'exister, car tant qu'il n'y a qu'un tenant les deux sont
   équivalentes et l'ancienne reste une protection supplémentaire.
4. Exceptions conservées globales : `users.username`, `refresh_tokens.token_hash`,
   `revoked_tokens.jti`, `report_snapshots.verification_token_hash`.

### Comment gérer les foreign keys ?

Ajouter `UNIQUE (tenant_id, id)` sur chaque parent, puis remplacer
`FOREIGN KEY (parent_id) → parent(id)` par
`FOREIGN KEY (tenant_id, parent_id) → parent(tenant_id, id)` (`NOT VALID` puis `VALIDATE`).
Une référence inter-tenant devient structurellement impossible, y compris pour
un code qui oublierait le filtre. FK vers une table GLOBAL : simple, sans tenant.
FK vers `users` (GLOBAL) : simple, complétée par une vérification applicative
de membership.

### Comment rollback ?

Chaque étape est réversible sans perte tant que la contraction n'a pas eu lieu :
`DISABLE`/`NO FORCE` RLS et `DROP POLICY` ; `DROP NOT NULL` ; suppression des
index composites ; `DROP COLUMN tenant_id` (donnée recalculable : tenant unique).
Les contractions (suppression d'une UNIQUE globale) sont séparées et
n'interviennent qu'après validation. Chaque migration a un `downgrade()` testé
par `test_alembic_migrations.py` (upgrade → downgrade → upgrade).

### Comment restaurer un tenant ?

Outillage à construire (lot dédié, avant le second tenant réel) :
1. Restaurer la sauvegarde complète dans une **base de transit isolée** (rôle `ruggylab_backup`).
2. Extraire le tenant par `COPY (SELECT … WHERE tenant_id = :t) TO …`, table par
   table dans l'ordre topologique des FK.
3. Dans la base cible : purge contrôlée du tenant (ou base vierge), import,
   remappage des séquences si collision, contrôles d'orphelins et de
   `tenant_id` étranger = 0.
4. Double validation humaine ; rapport de restauration archivé.
Un tenant en silo (option D) se restaure par simple restauration de son instance.
