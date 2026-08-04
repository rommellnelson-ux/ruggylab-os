# Plan de migration du registre Equipment — 2026

## Révision

- Révision : `20260724_0039`.
- Parent : `20260723_0038`.
- Nature : additive et réversible sur base de test.

## Upgrade

1. Ajouter neuf colonnes compatibles à `equipments`.
2. Créer l'index unique nullable de l'identifiant d'actif et l'index d'unité.
3. Créer `equipment_interfaces`.
4. Créer `equipment_qualifications`.
5. Créer `equipment_approved_analytes`.
6. Créer `equipment_documents`.

La migration ne supprime, ne renomme et ne convertit aucune colonne existante.
Elle ne crée aucune interface, qualification, analyte ou preuve. Les champs
d'identité historiques restent `NULL`; `clinical_use=false` empêche toute
activation implicite.

## Downgrade de test

Le downgrade supprime d'abord les quatre nouvelles tables dans l'ordre des FK,
puis les index et colonnes additives. Il ne constitue pas une procédure de
rollback de production : après saisie de preuves, un retour applicatif doit
conserver la base migrée jusqu'à décision DBA/qualité.

## Qualification attendue

- SQLite frais : upgrade head.
- SQLite : upgrade, downgrade base, upgrade head.
- SQLite synthétique au head 0038 avec une ligne Equipment : identité
  historique inchangée, nouveaux champs inconnus nuls, aucune interface ou
  qualification créée.
- PostgreSQL 16 : upgrade, downgrade base, upgrade head dans le job CI.
- PostgreSQL 16 : transaction de registre et rollback vérifiés depuis une
  nouvelle session.
- PostgreSQL 16 : allocation concurrente des versions sérialisée par équipement.
- Head unique contrôlé par Alembic et `pg_restore_verify.ps1`.

## Rollback applicatif

Le code reste fail-closed si les nouvelles tables sont vides. Une restauration
à un ancien binaire après upgrade n'est autorisée qu'après vérification de sa
tolérance aux colonnes/tables additives. Aucun downgrade ne doit être lancé sur
une base réelle dans le cadre de ce lot.

## Données exclues

Aucune donnée patient, marque/modèle/firmware réel, numéro de série complet,
adresse, port, secret, protocole, méthode, unité ou qualification réelle n'est
introduit par la migration ou la documentation.
