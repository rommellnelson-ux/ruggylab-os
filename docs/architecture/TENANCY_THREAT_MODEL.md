# Modèle de menaces — isolation multi-tenant

Référence : [ADR-001](ADR-001-MULTI-TENANCY.md). Base `b40021c`.
Actif protégé : la confidentialité et l'intégrité des données d'un tenant vis-à-vis
de tout autre tenant, et vis-à-vis de l'exploitant plate-forme hors accès justifié.

« Existing control » décrit **ce qui existe aujourd'hui dans le code** : il n'y a
pas de tenant, donc la plupart des contrôles sont absents ; quand un contrôle
d'unité existe (`app/services/patient_access.py`), il est cité avec ses limites.

Convention de nommage des tests requis : `tests/tenancy/test_<menace>.py`,
exécutés sur PostgreSQL réel avec le rôle `ruggylab_app` (non superutilisateur)
et deux tenants A/B jetables. Aucun de ces tests n'est créé dans ce lot ; ils
constituent le périmètre du **harness d'isolation**.

| # | Threat | Attack path | Existing control | Required control | Required automated test | Residual risk |
|---|---|---|---|---|---|---|
| T01 | IDOR / BOLA | Utilisateur de A appelle `GET /patients/{id}` avec un id de B | Filtre `unit` sur patients/échantillons/résultats seulement ; ids entiers séquentiels devinables | RLS tenant + chargement par `(tenant_id, id)` ; 404/403 uniforme | Pour chaque route `/{id}` de l'OpenAPI : un id de B demandé depuis A → refus | Routes futures non couvertes si le test ne parcourt pas l'OpenAPI automatiquement |
| T02 | Cross-tenant read | Liste/recherche sans filtre tenant | Aucun (mono-organisation) | RLS `USING` | Requête sans `WHERE tenant_id` en contexte A → 0 ligne de B | Contournement par rôle privilégié (T18) |
| T03 | Cross-tenant update | `PATCH` sur une ressource de B | Aucun | RLS `USING` + `WITH CHECK` ; `tenant_id` non modifiable (trigger) | `UPDATE` sans filtre en contexte A → 0 ligne de B modifiée ; `UPDATE … SET tenant_id = B` → refus | — |
| T04 | Cross-tenant delete | `DELETE` sur une ressource de B | Aucun | RLS `USING` | `DELETE` sans filtre en contexte A → lignes de B intactes | — |
| T05 | Enumeration | Codes 403 vs 404 différents, ids séquentiels | Aucun | Réponse uniforme (H4) ; à terme identifiants non séquentiels exposés | Id de B existant vs inexistant → même statut, même corps, temps comparable | Canal temporel résiduel |
| T06 | Search leakage | `?q=` sur nom/IPP renvoie des patients de B | Filtre `unit` partiel | RLS ; index de recherche par tenant | Recherche d'un nom présent uniquement chez B depuis A → vide | Moteur de recherche externe futur |
| T07 | Count leakage | `total` de pagination, tableaux de bord, statistiques | Aucun | Agrégats sous RLS ; pas de `COUNT` en rôle privilégié | Compteurs A inchangés après insertion de N lignes dans B | — |
| T08 | Report leakage | Rapports TAT, épidémio, registre, bench radar agrègent tout | Filtre `unit` partiel (`epidemiology_service`, `tat_service`) | Rapports sous TenantContext ; rapports plate-forme seulement via PlatformAdminContext | Rapport en A identique avant/après injection de données B | Rapports plate-forme mal étiquetés |
| T09 | Export leakage | Exports CSV/FHIR/PDF de masse | Aucun au niveau tenant | Export sous RLS ; nom de fichier et en-tête incluent le tenant ; audit d'export | Export complet en A ne contient aucun identifiant de B | — |
| T10 | Foreign-key reference leakage | Créer un `exam_order` de A pointant vers `patient_id` de B ; message d'erreur FK révélant l'existence | Aucun | FK composites `(tenant_id, x_id)` ; erreurs d'intégrité génériques | Insertion référant une ligne de B → refus sans divulgation | — |
| T11 | Cache leakage | Clé Valkey = chemin + query + user_id ; un utilisateur multi-tenant obtient la réponse d'un autre tenant | Clé par `user_id` | Préfixe `t:{tenant_id}:` obligatoire ; décorateur qui refuse sans TenantContext | Même utilisateur, deux tenants, même URL → réponses distinctes | Clés écrites hors décorateur |
| T12 | Background-job leakage | Job sans tenant, ou exécuté avec le contexte du job précédent | Aucun ; scheduler et outbox globaux | `tenant_id` obligatoire dans la charge utile ; `SET LOCAL` par transaction ; refus sans contexte | Job sans tenant sur table tenantisée → 0 ligne + erreur ; deux jobs successifs A puis B ne se contaminent pas | Jobs plate-forme mal classés |
| T13 | File leakage | `image_url` / `storage_reference` / `data/microscopy/...` devinables, servis sans contrôle tenant | Répertoire unique | Préfixe `tenants/{tenant_id}/` ; service de fichiers qui revérifie l'appartenance ; URLs signées courtes | Fichier de B demandé avec session A → refus | Copies hors application (sauvegardes) |
| T14 | WebSocket / pub/sub leakage | Canal Valkey unique `NOTIF_CHANNEL` diffusé à tous les workers | Filtrage par utilisateur côté push | Événements porteurs de `tenant_id` ; filtrage par TenantContext de la connexion ; canaux préfixés | Événement critique de B jamais reçu par un WebSocket A | — |
| T15 | Superadmin abuse | Exploitant lit des dossiers patients sans motif | `admin` actuel voit tout (et n'est pas distingué d'un admin plate-forme) | PlatformAdminContext explicite, motif + ticket + expiration, audit immuable, pas d'accès clinique par défaut | Accès plate-forme sans justification → refus ; tout accès journalisé | Collusion / abus d'un exploitant légitime |
| T16 | Missing TenantContext | Route oubliée sans dépendance tenant ; `set_config` absent | N/A | Dépendance globale + listener `after_begin` + RLS fail-closed | Route appelée sans contexte → 403 ; session BD sans `app.tenant_id` → 0 ligne | — |
| T17 | Forged TenantContext | Client envoie `X-Tenant-ID: B` ou modifie le claim | N/A | Membership vérifié côté serveur à chaque requête ; claim signé, recoupé avec la base | En-tête/claim B pour un utilisateur sans membership B → 403 | — |
| T18 | Direct SQL bypass | Code utilisant le rôle superutilisateur ; `text()` brut ; outil d'admin | **Application en superutilisateur propriétaire** (P0) | Rôle `ruggylab_app` NOSUPERUSER NOBYPASSRLS non propriétaire ; FORCE RLS | Le test « filtre oublié » échoue en superutilisateur et réussit avec `ruggylab_app` | Rôles de sauvegarde/migration |
| T19 | Backup leakage | Dump complet remis à un tenant ; restauration test exposée | Sauvegarde globale unique | Chiffrement ; export par tenant outillé ; jamais de dump global remis à un tenant | Export d'un tenant ne contient aucune ligne d'un autre | Accès physique aux sauvegardes |
| T20 | Wrong-tenant restore | Restauration de A écrase/injecte dans B ; collisions d'id | Aucune procédure par tenant | Restauration logique par tenant dans une base de transit, vérification `tenant_id`, remappage d'ids, double validation | Restauration de A dans une base contenant B → B inchangé, A complet | Erreur humaine pendant le PRA |
| T21 | Logs / metrics leakage | Logs contenant des PII de plusieurs tenants dans un même flux ; labels Prometheus à forte cardinalité exposés | Test `test_no_patient_attributes_in_logs` (pas de PII) | `tenant_id` (pas de nom) en champ structuré ; accès aux logs par tenant ; pas d'id patient en label | Les logs d'une requête A ne contiennent aucun identifiant de B | Accès exploitant aux logs |
| T22 | « Pool partagé » `unit IS NULL` (spécifique as-built) | Patient non affecté visible par tous les techniciens ; technicien sans unité = transversal | C'est le comportement actuel (fail-open) | À la tenantisation : pas d'équivalent au niveau tenant ; au niveau unité, H6 | Patient sans unité invisible pour un technicien d'une autre unité (si H6 accepté) | Décision métier |
| T23 | Ingestion analyseur mal routée | Message HL7 portant un code-barres de B reçu par une interface de A | Unicité globale `samples.barcode` | Tenant dérivé de l'interface réceptrice ; rapprochement par (tenant, barcode) | Message sur interface A avec barcode de B → rejet, pas de rattachement | Configuration réseau erronée |
| T24 | Vérification publique de compte rendu | `verification_token_hash` global résolu sans contexte | Lookup public | Fonction `SECURITY DEFINER` renvoyant un minimum non identifiant | Jeton valide → seul le statut d'authenticité ; jeton d'un autre tenant ne révèle rien de plus | Fuite de jeton |
