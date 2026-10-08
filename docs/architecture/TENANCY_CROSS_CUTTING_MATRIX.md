# Matrice transverse — tenancy hors base de données

RLS ne protège que les requêtes SQL. Cette matrice recense, depuis le code de
`b40021c`, chaque mécanisme transverse, son état actuel et l'exigence cible.

| Domaine | Implémentation as-built | Dimension tenant aujourd'hui | Exigence cible | Menace liée | Priorité |
|---|---|---|---|---|---|
| Authentification | JWT + `auth_version`, `refresh_tokens`, `revoked_tokens` (`app/api/v1/endpoints/login.py`, `app/core/security.py`) | Aucune | Claim `tid` signé émis après sélection d'un membership ; revérifié à chaque requête | T17 | P0 (harness) |
| RBAC | `UserRole` unique sur `users.role` ; `require_officer` / `require_admin` / `require_finance` / `forbid_accountant` dans `app/api/deps.py` | Aucune | Rôles portés par `tenant_memberships` ; `admin` = admin de tenant | T15 | P1 |
| Cloisonnement d'unité | `app/services/patient_access.py` (10 endpoints, 6 services), chaîne libre, fail-open (`unit IS NULL`, technicien sans unité) | Aucune | Filtre d'unité **dans** le tenant, par `org_unit_id`, fail-closed (H6) | T22 | P1 |
| Session BD | `app/db/session.py`, rôle superutilisateur `ruggylab` | Aucune | `ruggylab_app` ; `SET LOCAL app.tenant_id` par transaction ; listener de garde | T16, T18 | **P0** |
| Migrations | Alembic, même rôle que l'app ; `target_metadata` incomplète (46/49) | N/A | Rôle `ruggylab_migrator` ; métadonnée complète | — | P1 |
| Cache Valkey | `app/core/cache_decorator.py` : clé = chemin + méthode + query + `user_id` | Aucune | Préfixe `t:{tenant_id}` obligatoire, refus sans contexte | T11 | P1 |
| Pub/Sub | `app/services/redis_notification.py` : canal unique `NOTIF_CHANNEL` | Aucune | `tenant_id` dans chaque événement ; filtrage à la livraison | T14 | P1 |
| WebSocket | `app/api/v1/endpoints/notifications.py` : push périodique filtré par utilisateur/unité | Aucune | Connexion liée à un TenantContext figé à l'ouverture | T14 | P1 |
| Rate limiting / quotas | `app/core/rate_limit.py`, `user_quota.py`, `login_rate_limit.py` | Par utilisateur/IP | Ajouter quota par tenant (voisin bruyant) | — | P2 |
| Scheduler | `app/scheduler.py` : nettoyage jetons (TECHNICAL), synchro CSA (singleton) | Aucune | Jobs tenantisés itèrent explicitement par tenant ; jobs TECHNICAL restreints aux tables TECHNICAL | T12 | P1 |
| Outbox rapports | `report_delivery_outbox` + service | Aucune | `tenant_id` sur la ligne ; worker par transaction tenant | T12 | P1 |
| Jobs IA paludisme | `malaria_analysis_jobs`, `app/services/malaria_ai.py` | Aucune | `tenant_id` dans la charge utile ; images préfixées | T12, T13 | P2 |
| Ingestion analyseurs | `app/analyzer_gateway.py`, `app/services/analyzer_ingestion.py`, `interfacing/` ; rapprochement par `samples.barcode` global | Aucune | Tenant/site dérivés de `equipment_interfaces` ; rapprochement par (tenant, barcode) | T23 | P1 |
| Intégration CSA | `app/services/csa_sync/*`, `csa_sync_state` singleton | Aucune | Selon TBD-3 | T12 | P2 |
| Fichiers | `MICROSCOPY_STORAGE_DIR = data/microscopy`, `image_url`, `storage_reference` | Aucune | Préfixe `tenants/{id}/` ; service de lecture qui revérifie | T13 | P1 |
| PDF / comptes rendus | `pdf.py`, `report_signing.py`, `report_snapshots` | Aucune | Instantané lié au tenant ; vérification publique minimale | T09, T24 | P1 |
| Exports | FHIR (`fhir_builder.py`), CSV (`csv_safety.py`), registre | Aucune | Sous RLS ; audit d'export ; tenant dans les métadonnées | T09 | P1 |
| Audit | `audit_events` + `app/services/audit.py` | Aucune | `tenant_id` NOT NULL ; flux plate-forme séparé | T15 | P1 |
| Logs | `app/core/logging_config.py` (JSON) | Aucune | Champ `tenant_id` structuré ; jamais de nom de tenant ni PII | T21 | P2 |
| Métriques | `app/core/metrics.py`, labels de route | Aucune | Label `tenant` borné, pas d'identifiant patient | T21 | P2 |
| Sauvegarde / PRA | `scripts/` backup/restore, `docs/ROLLBACK_AND_RECOVERY_RUNBOOK_2026.md` | Instance entière | Export/restauration par tenant (voir plan) | T19, T20 | P1 |
| Secrets | `app/core/secrets_manager.py` (Azure Key Vault, variable `tenant_id` = tenant Azure AD) | Collision de nom | Renommer en `azure_tenant_id` | — | P2 |
| Observabilité Grafana | `monitoring/` | Aucune | Tableaux par tenant restreints ; vue plate-forme réservée | T21 | P2 |
