# Registre des risques d'audit — RuggyLab OS — 2026

## Règles de lecture

- **Fait** : directement observé dans le code, une migration, un test ou une CI.
- **Scénario** : conséquence plausible, pas un incident observé.
- **Confiance** : élevée lorsque le scénario a été reproduit ; moyenne lorsque
  la conclusion dépend d'une politique ou de données historiques non consultées.
- **Statut** : corrigé, non confirmé, accepté, ouvert ou escaladé.

## Constats corrigés ou non confirmés

| ID | Priorité / nature | Preuve et scénario | Protection / test | Correction et statut |
|---|---|---|---|---|
| R1 | P0 clinique, intégrité | `exam_orders.collect_order_sample` acceptait un échantillon d'un autre patient ; un rapport pouvait agréger le mauvais résultat. Confiance élevée. | `test_clinical_safety_r1_r2_r4.py`, preuve de verrou PostgreSQL. | Contrôle patient avant idempotence, `FOR UPDATE`, statuts terminaux. PR #85. **Corrigé**. |
| R2 | P1 sécurité, clinique | `results.create_result` pouvait écrire hors unité avant stock/audit. Confiance élevée. | Matrice rôles/unités et absence d'effet après 403. | `forbid_accountant` et contrôle patient/unité avant effet. PR #85. **Corrigé**. |
| R3 | P1 sécurité | `results.amend_result` est réservé à `require_officer`; OFFICER/ADMIN sont transversaux par politique. | Tests RBAC et dépendance de route. | Aucun contournement confirmé selon cette politique. À rouvrir si les officiers deviennent unitaires. **Non confirmé**. |
| R4 | P1 intégrité, traçabilité | Signature et libération pouvaient être séparées par un commit, laissant signature sans snapshot/outbox. Confiance élevée. | Rollbacks simulés et tests de réémission. | Transaction unique et réponse matérialisée avant commit. PR #85. **Corrigé**. |
| R5-AUTO | P1 intégrité | `samples._next_lab_number` utilisait une allocation non sérialisée. Deux requêtes pouvaient produire le même numéro. | `test_lab_numbering_r5_postgres.py`. | Verrou advisory annuel et maximum valide + 1. PR #87. **Corrigé** pour l'allocation automatique. |
| R6 | P1 intégrité | Rejeux concurrents automate/DH36 pouvaient dupliquer résultat, audit ou stock. | `test_analyzer_idempotency_r6_postgres.py`. | Sérialisation par clé, collision reconnue, transaction DH36 atomique. PR #86. **Corrigé**. |
| RBAC-01 | P1 sécurité | Les lectures/mutations d'échantillon ne filtraient pas toutes l'unité patient. | `test_sample_unit_rbac.py`. | Filtre partagé et contrôles avant écriture. PR #88. **Corrigé**. |
| RBAC-02 | P1 sécurité | Alertes, rapports, TAT et WebSocket exposaient des résultats inter-unités ; un socket survivait au logout. | `test_clinical_reporting_rbac.py`. | Scope patient/unité et revalidation de session par émission. PR #89. **Corrigé**. |
| PRE-01 | P1 clinique | Un échantillon `Annule` pouvait encore produire un résultat ou être réactivé. | Tests de tous les producteurs + concurrence PostgreSQL. | Verrou échantillon et invariant terminal. PR #90. **Corrigé**. |
| AUD-01 | P1 traçabilité | Six mutations centrales pouvaient committer sans événement métier. | `test_clinical_lifecycle_audit.py`, rollback si audit échoue. | Audit dans la transaction existante, payload minimal. PR #91. **Corrigé**. |
| OPS-01 | P1 exploitation | `pg_restore_verify.ps1` acceptait une base scratch arbitraire, checksum absent et retour `pg_restore` non fatal. | 12 contrôles statiques ; aucun SGBD réel touché pendant la correction. | Liste blanche, checksum obligatoire, `--exit-on-error`, head testé. PR #92/#98. **Corrigé**. |
| QMS-01 | P1 intégrité | Deux transitions NC/CAPA pouvaient partir du même état et produire des audits contradictoires. | `test_quality_transaction_postgres.py`. | `FOR UPDATE`, audit CAPA atomique. PR #93. **Corrigé**. |
| FIN-01 | P1 intégrité | Encaissements concurrents : deux mouvements mais `paid_xof` perdu ; BNPL committé avant facture. | `test_finance_transaction_postgres.py`. | Verrous et transaction BNPL/facture/audit unique. PR #94. **Corrigé**. |
| IMG-01 | P1 clinique, confidentialité | Imagerie sur échantillon annulé, jobs concurrents et données sensibles dans erreurs/audits. | Tests SQLite et PostgreSQL ciblés. | Verrous, déduplication et minimisation. PR #95. **Corrigé**. |
| EPI-01 | P1 sécurité | Le dashboard épidémiologique agrégait des résultats hors unité. | `test_epidemiology_unit_scope.py`. | Scope patient/unité ; transversalité admin/officier conservée. PR #96. **Corrigé**. |
| FHIR-01 | P1 traçabilité | L'export FHIR résultat n'était pas audité ; l'audit patient répétait l'IPP. | `test_fhir_audit_safety.py`. | Audit obligatoire avant réponse, payload minimisé. PR #97. **Corrigé**. |
| AUTH-01 | P1 sécurité | Anciens JWT/refresh encore utilisables après mot de passe ; réactivation ressuscitait la session. | Tests rouges HTTP et deux courses PostgreSQL. | `User.auth_version`, révocation globale, ordre de verrou utilisateur→token. PR #98. **Corrigé**. |
| CI-OPEN-01 | P3 exploitation | Actions JavaScript Node 20 et PR d'intégration sans déclenchement CI. | CI cumulative, Playwright Node 24 et SHA d'actions contrôlés. | `setup-node`/`upload-artifact` v6 épinglés, cible de PR intégration ajoutée. PR #100. **Corrigé**. |
| DEP-PILLOW-01 | P2 sécurité | `pip-audit` a signalé 20 avis sur Pillow 12.2.0, tous corrigés en 12.3.0. | CI `30047965217` : installation 12.3.0, 1 308 tests et aucun avis connu. | Pin 12.3.0 dans une PR dédiée. PR #101. **Corrigé**. |
| PR80-CLIN-01 | P1 clinique, intégrité | Le qualitatif validait/classait critique sans règle et le POCT générique appliquait un catalogue non homologué. | Tests de non-validation/non-criticité et refus POCT avant effet ; CI #107 `30056391313`. | Qualitatif non validé/non critique, POCT fail-closed, interfaces désactivées. PR #107. **Corrigé techniquement ; workflow futur non homologué**. |
| IMG-OPEN-01 | P1 clinique | Le fallback paludisme déterministe pouvait écrire dans `Result` et poser `is_critical`. | Modèle absent/erreur et inférence simulée : aucune mutation clinique. | Heuristique supprimée, échec explicite et sortie non clinique sur le job. PR #107. **Corrigé**. |

## Risques ouverts ou escaladés

| ID | Priorité / nature | Fichier, symbole, preuve | Scénario / conséquence | Protection existante | Test à écrire | Traitement / statut |
|---|---|---|---|---|---|---|
| LAB-OPEN-01 | P1 intégrité | `app/models/ruggylab_os.py:Sample`, `Sample.lab_number` vers la ligne 115 ; `app/schemas/sample.py:SampleBase.lab_number` vers la ligne 41 ; `samples.create_sample` vers 151. Colonne non unique, valeur client libre. Confiance élevée sur le code, inconnue sur l'historique. | Deux échantillons portent le même identifiant imprimé/recherché. | Génération automatique sérialisée ; code-barres unique. | Valeurs explicites concurrentes + inventaire de doublons sur copie autorisée. | Contrainte/backfill potentiellement sensibles. Décision D1. **Escaladé**. |
| ACQ-OPEN-01 | P1 intégrité | `results_qualitative.submit_qualitative_result` crée toujours un `Result` sans clé d'acquisition ; POCT est désormais fail-closed. | Rejeu d'une saisie qualitative : doublon ; déduplication naïve : suppression d'une observation légitime. | Transaction locale ; statut annulé refusé ; résultat non validé/non critique. | Deux appels qualitatifs identiques séquentiels et concurrents avec futur identifiant d'acquisition. | Contrat métier absent. Décision D2. **Escaladé, périmètre réduit**. |
| ACQ-OPEN-02 | P1 intégrité, exploitation | `raw_tcp_listener._handle_client` appelle `_store_frame` puis `_acknowledge` vers 225 ; en panne Redis `_store_frame` met en tampon mémoire vers 343. | Coupure du process après ACK : trame perdue et automate ne rejoue pas. | Tampon borné et replay vers Redis ; ACK après tentative de stockage. | Redis indisponible + arrêt simulé + comportement de retry instrument. | Décision ACK/stockage durable D3. **Escaladé**. |
| EPI-OPEN-01 | P1 sécurité | `EpiNotification` lignes 18–24 stocke patient/libellé/quartier sans unité ; `epi_notifications.list_notifications` vers 55 ignore le contexte utilisateur. | Personnel d'une unité lit une notification nominative d'une autre unité. | Comptable refusé ; transmission réservée à OFFICER ; audit. | Deux unités, notification avec/sans patient, matrice de visibilité. | Schéma/politique nécessaires. Décision D5. **Escaladé**. |
| FHIR-OPEN-01 | P1 intégrité, sécurité | `fhir_pharmacy.create_medication_dispense` vers 67 et `create_supply_delivery` vers 110 dépendent seulement d'un utilisateur actif ; builder fixe `status=\"completed\"` vers 415/555. | Un utilisateur produit une ressource « terminée » sans dispensation/livraison persistée. | Pydantic et logs minimisés ; aucun commit ni appel à un service tiers dans ces fonctions. | Rôle non autorisé ; référence inexistante ; statut dérivé d'un agrégat persisté. | Décision D6. **Escaladé**. |
| AUTH-OPEN-01 | P1 sécurité | `docs/ARCHITECTURE_AS_BUILT.md` classe la MFA privilégiée comme cible. | Compromission d'un secret privilégié suffisante pour accéder au système. | Rate limits, JWT versionné, révocation et secrets forts au démarrage. | Enrôlement, récupération, replay et révocation MFA. | Changement majeur d'auth/exploitation. Décision D7. **Escaladé**. |
| RESULT-OPEN-01 | P1 clinique, traçabilité | `results.amend_result` vers 512 remplace `data_points` en place ; audit contient ancien/nouveau et les snapshots signés sont versionnés. | L'historique analytique dépend d'une table d'audit elle-même mutable, plutôt que d'une chaîne de résultats immuable. | Révocation signature, audit détaillé, snapshots/outbox versionnés. | Deux amendements, reconstruction de chaîne, suppression/modification audit interdite. | Migration et règle de version clinique. Décision D8. **Escaladé**. |
| AUD-OPEN-01 | P2 sécurité, traçabilité | `AuditEvent` vers `app/models/ruggylab_os.py:275` n'a ni garde DB d'update/delete, ni scellement. | Un accès SQL privilégié altère la piste médico-légale. | API admin en lecture/export seulement ; audits atomiques. | Compte SQL applicatif incapable d'UPDATE/DELETE ; vérification de chaîne de hash éventuelle. | Permissions DB/rétention à définir. **Ouvert**. |
| FIN-OPEN-01 | P2 intégrité | `invoices.cancel_invoice` vers 260 refuse si payé, mais ne recherche pas un plan BNPL existant. | Facture annulée alors qu'un échéancier associé reste actif. | Verrou facture, audit, paiement interdit après annulation. | Facture non payée + plan actif + annulation. | Politique métier contradictoire non trouvée. **Escaladé**. |
| AUTH-OPEN-02 | P3 maintenabilité, sécurité | `login.login_access_token` passe les scopes du formulaire ; `deps.get_current_user` sait les vérifier, mais aucune route examinée n'utilise `Security(...scopes=...)`. | Un futur endpoint croit les scopes gouvernés alors qu'ils sont déclaratifs. | RBAC en base chargé à chaque requête. | Recherche statique imposant une source serveur des scopes dès la première route scopée. | Clarifier ou retirer ce mécanisme avant usage. **Ouvert**. |
| AUTH-OPEN-03 | P3 exploitation | Aucune route de récupération n'a été trouvée dans les routeurs/schémas inspectés. Confiance moyenne. | Perte de mot de passe : intervention DB/admin non formalisée. | Admin peut changer le mot de passe et invalide désormais les sessions. | Parcours de récupération approuvé et audit complet. | Confirmer le besoin et la procédure hors ligne. **Ouvert**. |
| GOV-ACCEPT-01 | P1 clinique | `docs/ARCHITECTURE_AS_BUILT.md` consigne `REQUIRE_VALIDATION_FOR_RELEASE=false` par décision du responsable. | Compte-rendu libéré sans validation biologique obligatoire. | Valeurs critiques acquittées ; décision et condition de réversibilité documentées. | UAT de la procédure provisoire puis activation à l'arrivée d'un validateur. | Risque explicitement **accepté** ; réévaluation obligatoire. |
| EQUIP-OPEN-01 | P1 clinique, intégrité, gouvernance | `app/models/ruggylab_os.py:Equipment` ne porte que l'identité minimale, localisation et dernière calibration ; aucun protocole, driver, qualification, méthode/analyte/unité ou version. | Activation d'un appareil sur un nom/port approximatif, ou impossibilité de prouver le périmètre homologué. | Interfaces et ingestion DH36 désactivées ; parseurs inconnus stubs ; POCT fail-closed. | Migration additive, reprise sans valeurs fabriquées, tests d'activation refusée/incomplète et historique de qualification. | Choix A/B dans `DEVICE_EQUIPMENT_REGISTRY_DECISION_2026.md`. **Escaladé avant migration**. |

## Contrôles récurrents

- Aucun P0/P1 ne doit être clos sans test synthétique et preuve PostgreSQL quand
  le risque dépend d'un verrou.
- Toute nouvelle migration doit maintenir le test du head attendu par
  `pg_restore_verify.ps1`.
- Toute route clinique doit vérifier rôle/unité avant stock, audit,
  notification ou commit.
- Toute sortie FHIR/PDF remise à un tiers doit être dérivée d'un état persisté et
  produire une piste d'audit atomique.
- Toute décision sur les constats escaladés doit être ajoutée ici avec date,
  responsable, option choisie et condition de réexamen.
