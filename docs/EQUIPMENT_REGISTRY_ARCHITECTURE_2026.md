# Architecture du registre Equipment — 2026

## Décisions applicables

`EQUIP-DEC-01` autorise l'option B : identité additive sur `equipments` et
sous-registres normalisés. `EQUIP-RBAC-01` autorise la séparation technique et
clinique décrite ci-dessous. Ces décisions donnent au logiciel la capacité de
contrôler une future homologation ; elles ne qualifient aucun appareil réel.

Tous les appareils réels restent **NON QUALIFIÉS / NON ACTIVABLES EN
CLINIQUE**.

## Architecture construite

```text
FastAPI /api/v1/equipments
  ├─ vue simple expurgée ───────────── get_current_active_user
  ├─ identité/interface/document ───── require_admin
  ├─ brouillon/soumission/version ──── require_admin
  ├─ approbation/suspension/disable ── require_officer
  └─ activation ────────────────────── require_admin
                │
                ▼
app.services.equipment_registry
  ├─ verrous de ligne sur mutations
  ├─ snapshots et immutabilité applicative
  ├─ calcul unique de readiness
  ├─ activation/désactivation centralisées
  └─ AuditEvent ajouté avant le commit
                │
                ▼
SQLAlchemy / PostgreSQL 16 ou SQLite de test
  Equipment 1─N Interface 1─N Qualification 1─N ApprovedAnalyte
       └────────N Document
```

Les services de mutation ne font aucun `commit`. L'endpoint ajoute la mutation
et l'audit dans la même session, puis effectue un commit unique. Une exception
d'audit, de validation ou de commit provoque un rollback. Mettre `enabled=true`
par schéma d'entrée est impossible : seul le service `enable_interface` peut
effectuer cette transition.

L'activation du registre ne démarre aucun listener, n'ouvre aucun port et ne
modifie aucune machine. Le démarrage opérationnel demeure un acte de
déploiement/commissioning distinct et non autorisé par ce lot.

## Matrice RBAC EQUIP-RBAC-01

| Opération | Rôle | Dépendance | Audit | Précondition | Refus |
|---|---|---|---|---|---|
| Vue simple expurgée | Agent actif hors comptable | `get_current_active_user` | Aucun | Scope unité démontrable | 401/403 |
| Vue détaillée/readiness | OFFICER, ADMIN | `require_officer` | Aucun | Équipement existant | 403/404 |
| Créer/modifier identité | ADMIN | `require_admin` | `equipment.identity.create/update` | Identifiants uniques | 403/409 |
| Créer/modifier interface | ADMIN | `require_admin` | `equipment.interface.create/update` | Équipement existant | 403/404/409 |
| Document technique | ADMIN | `require_admin` | `equipment.document.register` | Métadonnées uniquement | 403/409 |
| Brouillon/version/soumission | ADMIN | `require_admin` | `draft_create`, `draft_update`, `submit` | Snapshot complet | 403/422 |
| Approbation clinique | OFFICER, ADMIN | `require_officer` | `equipment.qualification.approve` | Snapshot inchangé | 403/409/422 |
| Activation | ADMIN | `require_admin` | `equipment.interface.enable` | Readiness complète | 403/422 |
| Désactivation/suspension | OFFICER, ADMIN | `require_officer` | `interface.disable`, `qualification.suspend` | Entité existante | 403/404/409 |

L'approbation et l'activation sont deux appels, deux horodatages et deux audits
distincts. Aucune exigence de deux personnes différentes n'est décidée. Une
séparation maker-checker renforcée reste une décision humaine future.

## Données exposées

La vue simple ne renvoie jamais numéro de série, identifiant d'actif, protocole,
driver, endpoint, configuration, preuve ou document. La vue détaillée masque le
numéro de série et remplace les références de stockage/endpoint par
`registered`. Le checksum est représenté par un booléen de présence.

Les audits du registre contiennent identifiant interne, action, version,
transition, rôle et motif codifié. Ils excluent numéro de série, endpoint,
secret, contenu documentaire, commentaire interne, résultat et donnée patient.
Les chaînes d'entrée sont normalisées ; une valeur composée uniquement
d'espaces est traitée comme absente et ne satisfait jamais une condition de
readiness.

## Intégration aux producteurs

`analyzer_ingestion` résout l'équipement par `asset_identifier`, exige une
interface entrante unique, activée et toujours qualifiée, puis vérifie les codes
d'analyte avant de verrouiller l'échantillon. Le contrôle à l'usage verrouille
aussi la ligne d'interface jusqu'au commit de l'ingestion.

`dh36_ingestion` exige une identité unique correspondant au numéro transmis,
applique la même vérification de readiness et refuse un analyte hors périmètre.
Le flag global DH36 et les listeners restent désactivés par défaut. Le POCT
reste fail-closed ; aucun profil réel n'est créé par la migration.

## Limites et durcissement restant

- L'immutabilité d'une qualification approuvée et de ses documents est garantie
  par le service, pas par trigger ou permissions SQL dédiées.
- Les références documentaires pointent vers un système externe autorisé ; le
  contenu des manuels n'est pas stocké.
- Le champ `unit` réutilise la notion texte existante ; aucun nouveau modèle de
  site ou d'unité n'est introduit.
- Une activation réelle exige encore les barrières D1, D2, D3, les manuels,
  mappings, essais et signatures de commissioning.
