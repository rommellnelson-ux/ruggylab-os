# Audit final de sécurité clinique — RuggyLab OS — 2026

## 1. Résumé exécutif

Cet audit statique et dynamique a porté sur la branche
`feat/acquisition-3-flux`, du 23 juillet 2026, sans accès à une base de
production, sans donnée réelle de patient et sans lecture de fichier
d'environnement.

Quatorze lots indépendants ont été qualifiés par tests synthétiques, CI
PostgreSQL 16, stack Docker, CodeQL et Playwright, puis fusionnés par les
PR [#85](https://github.com/rommellnelson-ux/ruggylab-os/pull/85) à
[#98](https://github.com/rommellnelson-ux/ruggylab-os/pull/98). Ils corrigent
notamment :

- une possibilité de rattacher une prescription à l'échantillon d'un autre
  patient ;
- des contournements du cloisonnement par unité ;
- des écritures partielles ou perdues sur rapports, automates, qualité,
  facturation et imagerie ;
- la réactivation d'anciennes sessions après changement sensible du compte ;
- des lacunes de traçabilité sur le cycle clinique et les exports FHIR ;
- des gardes insuffisantes dans la vérification des restaurations.

À l'issue des corrections, aucun P0 ouvert n'est connu. Cette formulation ne
constitue pas une preuve d'absence. Huit P1 restent **escaladés**, car leur
traitement impose une règle clinique, une politique métier, un nouveau contrat
d'idempotence ou une migration susceptible de rencontrer des données
historiques :

1. unicité des numéros de laboratoire fournis explicitement ;
2. idempotence des saisies POCT et qualitatives ;
3. acquittement du flux TCP brut lorsque Redis est indisponible ;
4. emploi du fallback paludisme non clinique ;
5. visibilité des notifications épidémiologiques non rattachables à une unité ;
6. autorité et sémantique des ressources FHIR pharmacie au statut `completed`.
7. MFA des comptes privilégiés et procédure de récupération ;
8. chaîne immuable de versions des résultats amendés.

Le registre détaillé est
[`AUDIT_RISK_REGISTER_2026.md`](AUDIT_RISK_REGISTER_2026.md).

## 2. Périmètre

Le périmètre inspecté couvre :

- architecture FastAPI, cycle de vie, routeurs, dépendances et middlewares ;
- sessions SQLAlchemy, commits, rollbacks, verrous et effets secondaires ;
- patients, prescriptions, échantillons, résultats, validation, valeurs
  critiques et TAT ;
- automates REST, DH36/HL7, TCP brut, POCT et résultats qualitatifs ;
- contrôle qualité, non-conformités, CAPA, équipements et réactifs ;
- pharmacie, CMU, facturation et BNPL ;
- rapports, signatures, snapshots, outbox et exports FHIR ;
- imagerie et analyse paludisme ;
- épidémiologie et notifications MADO ;
- authentification, révocation, rôles, unités et WebSocket ;
- audit, migrations, sauvegarde, restauration, Docker et CI.

Les valeurs critiques, intervalles de référence, unités, règles
d'auto-validation et règles diagnostiques n'ont pas été modifiés.

## 3. Méthode

Pour chaque flux significatif, l'analyse a suivi :

```text
route HTTP
→ dépendances FastAPI
→ schéma Pydantic
→ service métier
→ modèle/requête SQLAlchemy
→ frontière transactionnelle
→ effets secondaires
→ réponse HTTP
→ piste d'audit
```

Chaque défaut corrigé a suivi le cycle :

1. confirmation statique ;
2. test synthétique rouge ;
3. recherche des protections contradictoires ;
4. correction minimale ;
5. tests ciblés et connexes ;
6. preuve PostgreSQL lorsque SQLite ne porte pas le verrou ;
7. Ruff, format, mypy, Bandit et `git diff --check` ;
8. revue du diff ;
9. branche et PR isolées ;
10. CI complète sur le SHA exact ;
11. fusion uniquement après succès.

Les constats ouverts distinguent le fait observé, le scénario plausible et la
décision encore nécessaire. Une absence trouvée par recherche statique n'est
pas présentée comme une preuve absolue d'absence.

## 4. Architecture réelle

```text
Clients cockpit / API / WebSocket / automates
        │
        ▼
Caddy TLS (production compose)
        │
        ▼
FastAPI app.main:create_app
  ├─ middlewares sécurité, quotas, rate-limit, compression, observabilité
  ├─ /api/v1 → app/api/v1/api.py → routeurs métier
  ├─ templates HTML/JS et fichiers statiques
  └─ lifespan
       ├─ bootstrap DB
       ├─ fan-out Redis pour les workers web
       ├─ purge des jetons pour le rôle scheduler
       └─ DH36 pour le rôle analyzer-gateway
        │
        ▼
Dépendances auth/RBAC → schémas Pydantic → endpoints/services
        │
        ├─ SQLAlchemy Session par requête → PostgreSQL 16
        ├─ Redis 7 : fan-out, limitation, file TCP brute
        ├─ outbox transactionnelle de diffusion des rapports
        └─ effets externes bornés : WebSocket, PDF/FHIR, e-mail/webhook
```

La session est créée et fermée par `app.db.session:get_db`. Les endpoints et
services portent donc explicitement leurs `commit()` et rollbacks. Les
corrections de cet audit ont réduit les frontières multiples sur les flux
critiques et introduit des verrous PostgreSQL pour les courses démontrées.

Les principaux agrégats persistés sont :

- `User`, `RefreshToken`, `RevokedToken` ;
- `Patient`, `Sample`, `ExamOrder`, `ExamOrderItem`, `Result` ;
- `ReportSignature`, `ReportSnapshot`, `ReportDeliveryOutbox` ;
- `Reagent`, `StockMovement`, équipements et ratios ;
- messages DH36 et jobs d'imagerie ;
- QC, non-conformités et actions CAPA ;
- factures, paiements et plans BNPL ;
- événements d'audit et notifications épidémiologiques.

Le head Alembic audité est `20260723_0038`.

## 5. Modèle de menaces

### Actifs

- identité du patient et association prescription–échantillon ;
- résultats, statuts de validation et valeurs critiques ;
- rapports signés et versions diffusées ;
- piste d'audit médico-légale ;
- stock, réactifs, factures et encaissements ;
- jetons d'accès et de rafraîchissement ;
- sauvegardes et capacité de restauration.

### Acteurs et frontières

- technicien rattaché à une unité ou transversal ;
- officier et administrateur transversaux selon la politique actuelle ;
- comptable séparé du clinique ;
- automate/API technique ;
- service web, scheduler, gateway analyseur et worker de diffusion ;
- PostgreSQL, Redis et systèmes externes de notification.

### Scénarios prioritaires

- confusion ou substitution de patient ;
- lecture ou écriture horizontale inter-unités ;
- rejeu concurrent et double effet ;
- commit partiel avant audit ou diffusion ;
- session ancienne redevenue valide ;
- perte d'une trame acquittée ;
- génération d'une ressource clinique ou logistique sans preuve persistée.

## 6. Inventaire synthétique

| État | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| Corrigé et fusionné | 1 | 15 | 1 | 0 |
| Escaladé / décision humaine | 0 | 8 | 1 | 0 |
| Ouvert technique | 0 | 0 | 1 | 3 |
| Accepté explicitement | 0 | 1 | 0 | 0 |

Les totaux reflètent le registre au moment du présent rapport et ne couvrent
pas les risques impossibles à observer sans qualification réelle du laboratoire.

## 7. Constats corrigés

| ID | Priorité | Résultat |
|---|---|---|
| R1 | P0 | Identité patient vérifiée avant idempotence, prescription verrouillée, rattachement concurrent empêché. |
| R2 | P1 | Création manuelle de résultat refusée avant effet hors rôle/unité. |
| R4 | P1 | Signature, audits, snapshot et outbox réunis dans une transaction. |
| R5 | P1 | Allocation automatique annuelle sérialisée et fondée sur le plus grand numéro valide. |
| R6 | P1 | Rejeux REST automate et DH36 rendus atomiques et idempotents sous concurrence. |
| RBAC-01 | P1 | Échantillons cloisonnés par unité pour liste, scan, résumé et mutation. |
| RBAC-02 | P1 | Alertes, rapports, TAT et WebSocket filtrés par unité et session active. |
| PRE-01 | P1 | Statut `Annule` terminal sur tous les flux de résultat et de collecte. |
| AUD-01 | P1 | Audit atomique des mutations centrales du cycle clinique. |
| OPS-01 | P1 | Vérification de restauration gardée, checksum obligatoire et échec `pg_restore` fatal. |
| QMS-01 | P1 | Transitions NC/CAPA sérialisées et mises à jour CAPA auditées. |
| FIN-01 | P1 | Encaissements et synchronisation BNPL/facture sérialisés et atomiques. |
| IMG-01 | P1 | Imagerie bloquée sur échantillon annulé et soumissions concurrentes dédupliquées. |
| EPI-01 | P1 | Agrégats épidémiologiques cloisonnés par unité. |
| FHIR-01 | P1 | Exports FHIR cliniques audités avant délivrance, payload d'audit minimisé. |
| AUTH-01 | P1 | Sessions antérieures invalidées après mot de passe ou changement d'activation. |
| DOC-01 | P2 | Head Alembic du vérificateur de restauration maintenu par un test statique. |

R3, « amendement hors unité », n'a pas été confirmé comme contournement du
modèle courant : la route est limitée à `require_officer` et les OFFICER/ADMIN
sont intentionnellement transversaux. Ce verdict dépend de cette politique. Si
la transversalité change, le test doit être rouvert.

## 8. Constats ouverts

### P1 escaladés

- **LAB-OPEN-01** — `SampleCreate.lab_number` accepte une valeur client libre ;
  la colonne est indexée mais non unique. La génération automatique est
  sérialisée, pas les valeurs explicites ni l'historique.
- **ACQ-OPEN-01** — POCT et résultats qualitatifs créent un nouveau `Result` à
  chaque appel sans identifiant d'acquisition. Dédupliquer par seul échantillon
  serait potentiellement faux.
- **ACQ-OPEN-02** — le listener TCP acquitte après `_store_frame`, même si Redis
  a échoué et que la trame n'est que dans un tampon mémoire borné.
- **IMG-OPEN-01** — le fallback paludisme est explicitement non clinique mais
  écrit `malaria_ai` dans le résultat et peut positionner `is_critical`.
- **EPI-OPEN-01** — une notification MADO peut contenir `patient_label`,
  `residence_quarter` et `sample_barcode` sans unité persistée ; la liste est
  globale pour tout utilisateur clinique actif.
- **FHIR-OPEN-01** — les endpoints FHIR pharmacie sont des transformateurs sans
  état accessibles à tout utilisateur actif et émettent `completed` à partir du
  payload, sans preuve persistée de validation, facture ou réception.
- **AUTH-OPEN-01** — l'architecture documente la MFA privilégiée comme cible ;
  son ajout modifie le parcours d'authentification et l'exploitation.
- **RESULT-OPEN-01** — les amendements modifient la ligne `Result` en place. Les
  audits et snapshots préservent une trace, mais il n'existe pas de chaîne
  relationnelle immuable `version/previous_version_id`.

### P2/P3

- **AUD-OPEN-01, P2** — `audit_events` n'est pas immuable en base ; seule l'API
  exposée est en lecture.
- **FIN-OPEN-01, P2** — l'annulation d'une facture non encaissée ne vérifie pas
  explicitement l'existence d'un plan BNPL associé.
- **AUTH-OPEN-02, P3** — les scopes OAuth sont fournis lors du login et vérifiés
  par la dépendance, mais aucune route examinée n'en exige ; la politique
  effective repose sur les rôles.
- **AUTH-OPEN-03, P3** — aucune route de récupération de compte n'a été trouvée
  par la recherche statique ; l'absence fonctionnelle doit être confirmée par le
  responsable d'exploitation.
- **CI-OPEN-01, P3** — deux actions GitHub ciblent encore Node.js 20 et sont
  forcées par le runner sur Node.js 24.

## 9. Décisions humaines

### D1 — Numéro de laboratoire

- Problème : les numéros explicites peuvent être dupliqués.
- Option A : interdire les valeurs client et rendre la colonne unique après
  inventaire/backfill.
- Option B : conserver les valeurs externes, avec namespace/source et contrainte
  composite.
- Recommandation : B si des numéros d'instruments/HIS doivent être conservés,
  sinon A.
- Décision attendue : autorité du numéro, portée site/unité/année et plan de
  traitement des doublons historiques.

### D2 — Idempotence POCT/qualitatif

- Problème : un rejeu peut créer un second résultat et une seconde consommation.
- Option A : identifiant d'acquisition obligatoire et unique.
- Option B : fenêtre de déduplication dérivée de l'échantillon, appareil, examen
  et heure.
- Recommandation : A, car B peut supprimer une mesure clinique légitime.
- Décision attendue : source et durée de vie de la clé métier.

### D3 — ACK du TCP brut

- Problème : une trame en tampon mémoire peut être acquittée puis perdue.
- Option A : ne pas acquitter tant que l'écriture durable échoue.
- Option B : journal local durable avec replay, puis ACK.
- Recommandation : B si les automates tolèrent mal les connexions non acquittées.
- Décision attendue : contrat ACK/retry de chaque automate et support de stockage
  local autorisé.

### D4 — Fallback paludisme

- Problème : une heuristique non clinique modifie un résultat et son caractère
  critique.
- Option A : interdire toute écriture clinique lorsque le vrai modèle est absent.
- Option B : conserver une sortie démonstration séparée, impossible à valider ou
  libérer.
- Recommandation : A en exploitation ; B uniquement dans un profil démonstration.
- Décision attendue : profils autorisés et statut réglementaire du modèle.

### D5 — Notifications MADO

- Problème : les lignes sans patient/unité ne sont pas cloisonnables.
- Option A : exiger `patient_id` et dériver l'unité.
- Option B : ajouter une unité obligatoire indépendante du patient.
- Recommandation : B pour permettre les déclarations anonymes sans perdre le
  cloisonnement.
- Décision attendue : visibilité par unité, district et rôles transversaux.

### D6 — FHIR pharmacie

- Problème : `completed` ne correspond pas nécessairement à un fait persisté.
- Option A : endpoint de projection réservé, avec statut non conclusif.
- Option B : ressource construite uniquement depuis une dispensation/livraison
  persistée et autorisée.
- Recommandation : B.
- Décision attendue : rôles autorisés, agrégat source et moment exact où
  `completed` devient vrai.

### D7 — MFA privilégiée

- Problème : un secret unique compromis suffit pour un compte privilégié.
- Option A : TOTP avec codes de récupération gérés hors ligne.
- Option B : WebAuthn avec clés matérielles et procédure de secours.
- Recommandation : B pour ADMIN/OFFICER, TOTP comme solution transitoire.
- Décision attendue : rôles concernés, enrôlement, récupération et conservation
  des facteurs de secours.

### D8 — Version immuable des résultats

- Problème : un amendement remplace la ligne analytique vivante ; l'ancien état
  repose sur l'audit et les snapshots.
- Option A : table/version chaînée `previous_version_id`.
- Option B : journal d'événements immuable reconstruisant l'état.
- Recommandation : A, plus simple à interroger et à qualifier.
- Décision attendue : granularité de version, migration de l'historique et
  comportement des rapports/FHIR face aux anciennes versions.

### Décision déjà consignée

`docs/ARCHITECTURE_AS_BUILT.md` consigne le maintien temporaire de
`REQUIRE_VALIDATION_FOR_RELEASE=false`, décidé faute de biologiste validateur.
Ce risque de gouvernance est **accepté**, non corrigé par le présent audit. Il
doit être renversé dès l'affectation d'un validateur et accompagné d'une
procédure provisoire formelle.

## 10. Pull requests et commits de fusion

| PR | Objet | Fusion |
|---|---|---|
| #85 | R1, R2, R4 | `fa6e2cc` |
| #86 | R6 automate/DH36 | `dd6e876` |
| #87 | R5 numérotation | `2ee090b` |
| #88 | RBAC échantillons | `9f5c282` |
| #89 | RBAC alertes/rapports/TAT | `6f5bbff` |
| #90 | Échantillon annulé | `1a79b48` |
| #91 | Audit cycle clinique | `f0d85f0` |
| #92 | Restauration | `0d5fe60` |
| #93 | NC/CAPA | `5af692e` |
| #94 | Facturation/BNPL | `2222697` |
| #95 | Imagerie | `c386031` |
| #96 | Épidémiologie | `17e1c22` |
| #97 | FHIR clinique | `d5aeed8` |
| #98 | Sessions/authentification | `7cb6517` |

Toutes ciblent `feat/acquisition-3-flux`, jamais `main`.

## 11. Tests et CI

Le workflow final de la PR #98 est
[30013137207](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30013137207).
Il a validé :

- Ruff lint et format ;
- mypy ;
- Bandit ;
- 1 308 tests réussis et 15 ignorés dans la suite générale ;
- Alembic `upgrade`, `downgrade base`, puis `upgrade head` sur PostgreSQL ;
- tests de concurrence clinique, automate, numérotation, échantillon, qualité,
  finance, imagerie et authentification sur PostgreSQL, sans skip dans le job ;
- smoke et flux clinique E2E PostgreSQL ;
- stack Docker via proxy TLS, sauvegarde et rôles de process ;
- CodeQL ;
- Playwright ;
- build et publication de l'image.

Les jeux de tests de traçabilité sont listés dans le tableau de la section 17.

## 12. Différences SQLite/PostgreSQL

- SQLite ne porte pas la sémantique réelle de `SELECT FOR UPDATE` ni les verrous
  advisory PostgreSQL.
- Les preuves de concurrence utilisent donc PostgreSQL 16 dans le job
  `test-postgres`.
- Les JSON sont stockés en `JSONB` sur PostgreSQL et en `JSON` sur SQLite.
- L'enum `userrole` et les migrations de normalisation sont qualifiés sur
  PostgreSQL.
- La majorité des tests HTTP utilise une base SQLite isolée créée par test ;
  cela prouve les contrats applicatifs, pas les verrous de production.
- Les cycles Alembic sont joués sur les deux moteurs par les tests/CI.

## 13. Risques résiduels

Les risques principaux sont ceux de la section 8. S'y ajoutent les limites
documentées de qualification :

- aucun automate physique, serveur cible, UPS, VLAN, imprimante ou PRA réel n'a
  été qualifié pendant cet audit ;
- aucune donnée historique de production n'a été inspectée ; l'absence de
  doublon de numéro de laboratoire n'est donc pas connue ;
- les règles biologiques sont testées comme code, pas validées scientifiquement
  ni homologuées par un biologiste dans cette mission ;
- le système reste un monolithe modulaire mono-site ;
- FHIR est un sous-ensemble d'export, pas un serveur FHIR complet.

## 14. Limites de l'audit

- Audit réalisé sur le code et des données synthétiques.
- Aucun pentest réseau externe ni analyse d'infrastructure réelle.
- Aucun test de charge ou de durée sur plusieurs workers.
- Aucun exercice de restauration conduit sur le serveur de production.
- Aucune preuve d'organisation ISO 15189 n'est déduite des tests logiciels.
- Les recherches statiques ne prouvent pas l'absence de chemins hors dépôt.

## 15. Recommandations de production

Avant toute mise en service :

1. arbitrer D1 à D8 et implémenter les décisions dans des lots séparés ;
2. désactiver l'écriture clinique du fallback paludisme ;
3. inventorier les numéros de laboratoire historiques avant toute contrainte ;
4. qualifier serveur, stockage, UPS, réseau automates et imprimantes ;
5. exécuter une sauvegarde puis une restauration vérifiée sur l'environnement
   cible, avec copie hors site ;
6. confirmer les rôles transversaux et la visibilité MADO ;
7. mettre en place MFA pour les comptes privilégiés ;
8. restreindre les droits SQL applicatifs sur `audit_events` et définir
   rétention/export/scellement ;
9. activer la validation biologique obligatoire dès qu'un validateur est nommé ;
10. conserver les images et déploiements par SHA immuable.

## 16. Plan d'audit périodique

- À chaque PR : tests ciblés, lint, typage, sécurité, migrations et revue de
  frontières transactionnelles.
- Hebdomadaire : dépendances, alertes CI, erreurs d'outbox et échecs d'ingestion.
- Mensuel : revue des rôles/unités, sessions, exports d'audit et restaurations
  de test.
- Trimestriel : exercice de panne Redis/PostgreSQL, rejeu automate, charge et
  multi-worker.
- Semestriel : revue clinique des seuils, règles d'auto-validation, delta checks
  et documents libérés, conduite par une autorité compétente.
- Annuel : pentest indépendant, PRA complet et revue du modèle de menaces.

## 17. Tableau de traçabilité

| Constat | Test principal | SHA qualifié | PR | CI |
|---|---|---|---|---|
| R1/R2/R4 | `test_clinical_safety_r1_r2_r4.py`, `test_clinical_safety_postgres.py` | `05091fff` | #85 | [29990241885](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/29990241885) |
| R6 | `test_analyzer_idempotency_r6.py`, `test_analyzer_idempotency_r6_postgres.py` | `122cf7fe` | #86 | [29992197562](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/29992197562) |
| R5 | `test_lab_numbering_r5.py`, `test_lab_numbering_r5_postgres.py` | `8464dd36` | #87 | [29994457030](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/29994457030) |
| RBAC échantillons | `test_sample_unit_rbac.py` | `68eab17d` | #88 | [29995868586](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/29995868586) |
| RBAC rapports/TAT | `test_clinical_reporting_rbac.py` | `f73d4181` | #89 | [29999128969](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/29999128969) |
| Échantillon annulé | `test_preanalytic_cancelled_sample_safety.py`, variante PostgreSQL | `3e022101` | #90 | [30000679159](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30000679159) |
| Audit clinique | `test_clinical_lifecycle_audit.py` | `4b5e6bef` | #91 | [30001895875](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30001895875) |
| Restauration | `test_restore_verification_safety.py` | `13f6b582` | #92 | [30002950464](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30002950464) |
| NC/CAPA | `test_quality_transaction_safety.py`, variante PostgreSQL | `a0b126bc` | #93 | [30003959277](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30003959277) |
| Finance/BNPL | `test_finance_transaction_safety.py`, variante PostgreSQL | `8ea39397` | #94 | [30005954989](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30005954989) |
| Imagerie | `test_imaging_transaction_safety.py`, variante PostgreSQL | `f10b4011` | #95 | [30007648372](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30007648372) |
| Épidémiologie | `test_epidemiology_unit_scope.py` | `34426f53` | #96 | [30008813684](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30008813684) |
| FHIR | `test_fhir_audit_safety.py` | `868d963c` | #97 | [30010155639](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30010155639) |
| Sessions | `test_auth_refresh.py`, `test_auth_session_postgres.py` | `ee0be350` | #98 | [30013137207](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/30013137207) |
