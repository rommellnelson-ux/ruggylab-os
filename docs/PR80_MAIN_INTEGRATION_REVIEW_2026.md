# Revue d'intégration de la PR #80 vers `main` — 2026

## 1. Résumé exécutif

La PR #80 regroupe l'acquisition, quatorze lots correctifs #85 à #98 et le lot
documentaire #99. Le head initial qualifié `8562262` est fusionnable avec
`main@e96b63c`, sans conflit, revue « Changes requested », discussion non
résolue, fichier `.env` ni head Alembic concurrent.

La CI cumulative initiale `30032100788` est verte sur ce SHA. La revue
indépendante confirme les invariants transactionnels, RBAC, préanalytiques,
d'audit, de qualité, finance, imagerie, FHIR et authentification corrigés.

Quatre résiduels techniques ont été ouverts en lots séparés :

- PR #102 : formatage d'un exemple Markdown détecté par Ruff courant ;
- PR #100 : Actions et Playwright Node 24, plus CI sur la branche d'intégration ;
- PR #103 : assertion Prometheus rendue déterministe ;
- PR #101 : Pillow 12.3.0 après 20 avis `pip-audit` sur 12.2.0 ; CI
  `30047965217` verte et aucun avis connu.

Une contradiction clinique empêche toutefois de recommander la fusion sans
arbitrage : les nouveaux flux qualitatif/POCT introduisent des sémantiques de
validation et de criticité non approuvées dans les preuves trouvées. Le verdict
préparatoire est donc **NO-GO temporaire**.

## 2. Références exactes

| Élément | Référence |
|---|---|
| PR | `#80`, base `main`, head `feat/acquisition-3-flux` |
| Base initiale | `e96b63ccc902b7dad664ac44ba92ea7a86699485` |
| Head initial audité | `856226251fa835cc433e097c6ac62e1b582e9133` |
| CI initiale | `30032100788`, événement `pull_request`, succès |
| Head Alembic | `20260723_0038` |
| Head applicatif après correctifs techniques | `f938030274045d61169e422f94819723b849c04f` |
| CI PR #80 après correctifs | `30048611087`, succès sur `f938030` |
| Lot auto-validation | PR #104, CI `30048739217`, fusion `5f8b652` |

Le commit unique de `main` absent du head initial est un changement
`.github/dependabot.yml` (`e96b63c`), antérieur de quelques minutes au commit
d'acquisition. Aucun conflit clinique ou migration n'en résulte.

Le checkout original est resté volontairement intact avec ses trois changements
préexistants : `.env.example`, `docker-compose.yml` et
`PLAN_AMELIORATION.md`. Le fichier d'environnement n'a pas été ouvert. Toutes
les corrections ont été réalisées dans des worktrees dédiés.

## 3. Composition

### 3.1 Diff initial `main...8562262`

- 89 fichiers ;
- 9 424 ajouts, 354 suppressions ;
- 23 commits côté feature ;
- 1 commit unique côté `main` ;
- 2 migrations ;
- aucun fichier `.env` dans le diff.

Répartition observée :

| Catégorie | Fichiers |
|---|---:|
| CI | 1 |
| Documentation | 5 |
| Migrations | 2 |
| Modèles | 1 |
| Routes/endpoints | 17 |
| Schémas | 3 |
| Services | 23 |
| Tests | 26 |
| UI/statique | 3 |
| Scripts | 3 |
| Autres | 5 |

### 3.2 Traçabilité des PR

Les PR #85 à #99 sont toutes fusionnées dans
`feat/acquisition-3-flux`. Leurs merge commits ont été vérifiés comme ancêtres
du head initial. Aucune revue bloquante ni discussion non résolue n'a été
trouvée.

La méthode de fusion recommandée pour #80 est **merge commit**, afin de
préserver cette traçabilité. Aucun squash/rebase n'est recommandé.

## 4. Migrations et modèle

La chaîne Alembic est linéaire de 0001 à `20260723_0038`.

| Migration | Changement | Correspondance modèle |
|---|---|---|
| `20260723_0037` | `results.result_type`, nullable et indexé | `Result.result_type` présent. |
| `20260723_0038` | `users.auth_version`, non-null, défaut 0 | `User.auth_version` présent. |

Contrôles :

- upgrade head ;
- downgrade base sur base jetable ;
- nouvel upgrade head ;
- idempotence/historique linéaire ;
- tests PostgreSQL ;
- smoke et UAT.

Aucun head concurrent, migration dupliquée, changement de type divergent ou
colonne modèle sans migration n'a été observé. L'absence de données réelles
interdit toute conclusion sur les doublons historiques ou valeurs incompatibles.

## 5. Revue de sécurité et intégrité

| Invariant | Conclusion | Preuve principale |
|---|---|---|
| R1 patient/prescription/échantillon | Confirmé | Vérification même patient, verrou échantillon, idempotence. |
| R2 autorisation avant effet | Confirmé | Comptable et hors unité refusés avant stock/audit. |
| R4 rapport atomique | Confirmé | Signature, snapshot, audit et outbox dans une transaction. |
| R5 numéro automatique | Confirmé | Verrou advisory PostgreSQL annuel. |
| R6 automate/DH36 | Confirmé | Clé idempotente, verrou et transaction unique. |
| RBAC patient/unité | Confirmé | Patients, samples, results, alertes, rapports, TAT, WebSocket. |
| PRE Annule terminal | Confirmé | Verrou et invariant sur tous les producteurs examinés. |
| AUD audit atomique | Confirmé | Audit avant commit et rollback testé. |
| OPS restauration scratch | Confirmé statiquement/CI | Allowlist, checksum, échec fatal, head 0038. |
| QMS NC/CAPA | Confirmé | `FOR UPDATE` et audit atomique. |
| FIN facture/BNPL | Confirmé pour concurrence | Verrous et transaction unique. |
| IMG | Confirmé | Annulation et déduplication. |
| EPI agrégats | Confirmé | Filtre unité, rôles transversaux documentés. |
| FHIR résultat | Confirmé | Audit avant délivrance et payload minimisé. |
| AUTH | Confirmé | `auth_version`, révocation et ordre de verrou. |

Les scans Bandit, CodeQL et secrets sont verts. Un scan vert ne prouve pas
l'absence absolue de secret ou vulnérabilité ; le diff et les chemins ont aussi
été contrôlés statiquement sans ouvrir de fichier d'environnement.

## 6. Revue clinique

### 6.1 Garanties confirmées

- échantillon annulé terminal ;
- refus hors unité avant écriture ;
- valeur critique acquittée avant libération ;
- rapports signés par snapshot versionné ;
- audit FHIR résultat ;
- bioref additif, sans modification de `flags`/`is_critical` ;
- fallback ML identifié comme non réel dans les métadonnées.

### 6.2 PR80-CLIN-01 — décision bloquante

**Criticité : P1. Nature : clinique, intégrité et gouvernance. Confiance :
élevée sur le code, faible sur l'intention clinique.**

Preuves :

- `app/api/v1/endpoints/results_qualitative.py:submit_qualitative_result`
  marque `is_critical` lorsque la catégorie est `parasitology` et le résultat
  positif ;
- la même fonction renseigne `validator_id` et `is_validated=True` pour tout
  utilisateur actif non comptable ayant accès au patient ;
- `tests/test_results_qualitative.py:test_positive_parasitology_is_critical`
  impose cette sémantique mais les tests utilisent uniquement un administrateur ;
- `app/api/v1/endpoints/results_poct.py:submit_poct_batch` accepte un
  `device_model` correspondant à un équipement enregistré, puis applique le
  catalogue POCT central issu du Precis Expert sans vérifier le type/méthode ;
- le rapport d'audit initial affirme globalement qu'aucune règle critique ou
  diagnostique n'a été modifiée.

Scénarios plausibles :

- faux classement critique et fatigue d'alerte pour une parasitologie positive
  qui n'est pas définie comme critique par la politique locale ;
- sens clinique ambigu de `is_validated=True` si un technicien saisit le résultat ;
- interprétation d'un appareil/méthode POCT non homologué avec un catalogue qui
  ne lui appartient pas.

Protections présentes :

- utilisateur authentifié ;
- comptable refusé globalement ;
- contrôle patient/unité ;
- verrou et refus échantillon annulé ;
- vocabulaire fermé des analytes POCT ;
- équipement modèle/série enregistré ;
- transaction, audit et stock atomiques.

Tests nécessaires :

- matrice rôle/unité/validateur ;
- matrice catégorie/organisme/densité/criticité signée ;
- équipement de type différent et méthode/unité ;
- approval explicite de l'autorité clinique ;
- non-régression alertes, validation et rapports.

Décision attendue : approuver exactement ces sémantiques ou ordonner une
restriction/correction dédiée. Aucun seuil ou comportement n'est modifié par ce
rapport.

## 7. CI cumulative initiale

Run : `30032100788`, head `8562262`, succès.

| Job | Résultat |
|---|---|
| Ruff lint/format, mypy, Bandit, pytest, scans | Succès |
| PostgreSQL migrations + concurrence + smoke + UAT | Succès |
| Docker production, TLS, ports, backup, rôles | Succès |
| CodeQL | Succès |
| Playwright | Succès |
| Publication d'image | Skippée pour événement PR |

La stack Docker a construit l'image et qualifié compose. Le job de publication
GHCR était correctement skippé : aucune image n'a été publiée par cette CI.

Résultat principal : **1 308 tests réussis, 15 skips, 11 warnings**.<br>
Résultat PostgreSQL dédié : **11 tests réussis**.

## 8. Inventaire des 15 skips

### 8.1 Onze tests PostgreSQL, attendus et exécutés ailleurs

| # | Fichier / test | Raison | Autre job | Conséquence |
|---:|---|---|---|---|
| 1 | `test_analyzer_idempotency_r6_postgres.py::test_r6_concurrent_analyzer_replay_creates_one_result` | SQLite principal | Oui, passé | Couvert. |
| 2 | `test_analyzer_idempotency_r6_postgres.py::test_r6_concurrent_dh36_replay_returns_duplicate_and_consumes_once` | SQLite principal | Oui, passé | Couvert. |
| 3 | `test_auth_session_postgres.py::test_password_change_serializes_with_concurrent_login` | PostgreSQL requis | Oui, passé | Couvert. |
| 4 | `test_auth_session_postgres.py::test_password_change_serializes_with_concurrent_refresh` | PostgreSQL requis | Oui, passé | Couvert. |
| 5 | `test_clinical_safety_postgres.py::test_r1_competing_sample_attachments_are_serialized` | PostgreSQL requis | Oui, passé | Couvert. |
| 6 | `test_finance_transaction_postgres.py::test_concurrent_invoice_payments_preserve_their_sum` | PostgreSQL requis | Oui, passé | Couvert. |
| 7 | `test_finance_transaction_postgres.py::test_concurrent_duplicate_bnpl_payment_is_recorded_once` | PostgreSQL requis | Oui, passé | Couvert. |
| 8 | `test_imaging_transaction_postgres.py::test_concurrent_malaria_submissions_create_one_job` | PostgreSQL requis | Oui, passé | Couvert. |
| 9 | `test_lab_numbering_r5_postgres.py::test_r5_concurrent_generation_waits_for_committed_sequence` | PostgreSQL requis | Oui, passé | Couvert. |
| 10 | `test_preanalytic_cancelled_sample_postgres.py::test_result_and_cancellation_are_serialized` | PostgreSQL requis | Oui, passé | Couvert. |
| 11 | `test_quality_transaction_postgres.py::test_concurrent_nc_transitions_observe_committed_status` | PostgreSQL requis | Oui, passé | Couvert. |

### 8.2 Quatre skips ML non exécutés ailleurs

| # | Fichier / test | Raison | Autre job | Conséquence |
|---:|---|---|---|---|
| 12 | `test_malaria_mobilenetv2.py::test_onnx_classifier_is_real_model` | paquet `onnx` absent | Non | Chargement réel non qualifié. |
| 13 | `test_malaria_mobilenetv2.py::test_onnx_predict_from_image_file` | paquet `onnx` absent | Non | Inférence fichier non qualifiée. |
| 14 | `test_malaria_mobilenetv2.py::test_onnx_confidence_sums_to_one` | paquet `onnx` absent | Non | Sortie probabiliste non qualifiée. |
| 15 | module `tests/test_ml_pipeline.py` | PyTorch absent à la collecte | Non | Entraînement/export/validation non qualifiés. |

Ces quatre skips sont attendus par la politique de dépendances optionnelles mais
ne sont **pas acceptables pour activer la fonction clinique**. D4 impose
fail-closed tant qu'un job ML et une validation clinique ne les couvrent pas.

Les skips dynamiques CORS, quota et compression n'ont pas été pris dans cette
exécution : leurs conditions étaient actives et les tests ont réussi.

## 9. Résiduels techniques

### Corrigés par lots dédiés

- `CI-OPEN-01` : setup-node/upload-artifact v6 et Node 24, SHA épinglés.
- Format Ruff de la documentation.
- Test Prometheus non déterministe.
- Pillow 12.2.0 : 20 avis `pip-audit`, version corrective 12.3.0.

### Escaladés

- `AUD-OPEN-01` : immutabilité DB des audits nécessite droits/migration.
- `FIN-OPEN-01` : politique d'annulation facture avec BNPL.
- `AUTH-OPEN-03` : récupération de compte.
- `AUTH-OPEN-02` : scopes OAuth déclaratifs ; les rôles DB font actuellement
  autorité. Aucun comportement n'est modifié.

## 10. PR #81

La PR #81 contient une information unique sur les garde-fous ISO 15189 §5.8 et
une anomalie historique de traçabilité de branche. Son point ouvert sur
`apply_bioref_to_result` est obsolète au head de #80.

Traitement réalisé :

1. intégrer un document adapté `docs/AUTOVALIDATION_5_8.md` ;
2. lier `docs/INTERPRETATION.md` ;
3. corriger les commentaires techniques contradictoires ;
4. qualifier et fusionner la PR #104 vers la branche d'intégration ;
5. commenter puis fermer #81 comme superseded, sans perte d'information.

## 11. Changements opératoires

- deux nouvelles colonnes/migrations, dont `auth_version` ;
- rôles de processus web/scheduler/gateway et stack production qualifiés ;
- nouveaux flux POCT/qualitatif/TCP ;
- outbox de rapports et worker dédié ;
- procédures de backup/restauration renforcées ;
- Actions CI sous Node 24 ;
- mise à jour Pillow corrective.

Le worker Windows existant n'est pas une preuve de qualification de ces rôles :
il pointe vers un checkout mutable et sa CLI est incompatible.

## 12. Rollback recommandé

- fusion par merge commit ;
- aucune activation/déploiement automatique ;
- image par digest/SHA ;
- rollback applicatif vers le digest précédent si schéma compatible ;
- privilégier migration corrective vers l'avant ;
- downgrade uniquement après répétition scratch ;
- préserver outbox, audits et snapshots ;
- bloquer les flux qualitatif/POCT/ML non approuvés ;
- suivre `ROLLBACK_AND_RECOVERY_RUNBOOK_2026.md`.

## 13. Limites

- aucune base, donnée patient, automate, serveur cible ou service de production ;
- aucune lecture de fichier d'environnement ;
- aucun pentest externe ni test de charge longue durée ;
- aucune validation scientifique des référentiels/seuils ;
- aucun test réel du modèle paludisme ;
- aucune preuve sur les doublons historiques ;
- historique Windows du Planificateur désactivé ;
- scans automatiques non assimilés à une preuve d'absence.

## 14. Risques ouverts et décision recommandée

| Risque | Niveau | Effet sur décision |
|---|---|---|
| PR80-CLIN-01 | P1 clinique | Bloque la fusion tant que non arbitré. |
| D4 fallback paludisme | P1 clinique | Bloque tout profil clinique ML. |
| D1/D2/D3 | P1 intégrité | Bloquent les interfaces concernées avant pilote. |
| D5/D6/D7/D8 | P1 | Bloquent le périmètre concerné avant production. |
| Worker local | P1 exploitation | Bloque la diffusion via cette tâche. |
| Quatre skips ML | Qualification incomplète | Acceptables seulement si ML fail-closed. |

**Verdict : NO-GO temporaire.**

Autorisation attendue :

1. décision clinique sur PR80-CLIN-01 ;
2. confirmation D4 fail-closed ;
3. après CI finale verte, autorisation explicite de fusionner #80 par merge
   commit, sans déploiement ;
4. autorisation séparée pour toute modification/redémarrage du worker.
