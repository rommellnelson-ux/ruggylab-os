# Dictionnaire de données du registre Equipment — 2026

## `equipments`

Les colonnes historiques restent inchangées. Les colonnes suivantes sont
additives :

| Colonne | Type | Nullabilité/défaut | Règle |
|---|---|---|---|
| `manufacturer` | varchar(150) | NULL | Valeur inconnue non fabriquée |
| `model` | varchar(150) | NULL | Valeur inconnue non fabriquée |
| `device_family` | varchar(100) | NULL | Famille technique, pas une homologation |
| `firmware_version` | varchar(100) | NULL | Requise par le service d'activation |
| `unit` | varchar(100) | NULL | Même notion que `User.unit`/`Patient.unit` |
| `clinical_use` | boolean | false | Ne déclenche aucune activation |
| `lifecycle_status` | varchar(50) | NULL | `retired` bloque la readiness |
| `asset_identifier` | varchar(100) | NULL, unique | Identité interne stable |
| `updated_at` | datetime | NULL | Horodatage d'une mise à jour du registre |

La migration ne renseigne aucune de ces identités historiques, sauf
`clinical_use=false`.

## `equipment_interfaces`

| Colonne | Rôle |
|---|---|
| `equipment_id` | FK restrictive vers `equipments` |
| `stable_identifier` | UUID applicatif unique |
| `interface_type` | serial, usb_device, usb_storage, ethernet, file_import, manual, proprietary, unknown |
| `direction` | inbound, outbound, bidirectional, unknown |
| `endpoint_reference` | Référence externe expurgée, jamais connexion/secret |
| `protocol_name/version` | Protocole explicitement documenté |
| `driver_name/version` | Driver explicitement versionné |
| `configuration_version` | Version exacte de configuration |
| `enabled` | false par défaut ; modifiable uniquement par le service |
| `archived` | Retrait logique |
| `disabled_at/reason` | Trace de désactivation |
| `created_at/updated_at` | Traçabilité technique |

Les contraintes `CHECK` ferment les types et directions. Aucune interface n'est
créée par la migration.

Les actions de désactivation et de suspension n'acceptent pas de texte libre.
Le motif est choisi parmi : `manual`, `incident`, `maintenance`,
`qualification_expired`, `firmware_replacement`, `driver_change`,
`protocol_change`, `configuration_change`, `retirement` et
`governance_decision`.

## `equipment_qualifications`

La paire `(equipment_id, version)` est unique. Chaque version couvre une
interface précise et stocke un snapshot de fabricant, modèle, famille,
firmware, type d'interface, protocole, driver et configuration.

Statuts autorisés :

| Statut | Sens |
|---|---|
| `unqualified` | Brouillon initial |
| `documentation_pending` | Preuves incomplètes |
| `technical_testing` | Essais techniques en cours |
| `technically_qualified` | Technique terminée, sans approbation clinique |
| `clinical_review_pending` | Snapshot soumis |
| `clinically_approved` | Approbation explicite enregistrée |
| `suspended` | Usage immédiatement interdit |
| `expired` | Statut historisable ; l'expiration temporelle est aussi vérifiée à l'usage |
| `retired` | Version retirée |

`decision_reference`, `evidence_reference` et `document_ids_snapshot`
référencent les preuves sans stocker leur contenu. L'approbateur, son rôle et
les horodatages sont conservés. `superseded_by_id` lie une nouvelle version à
l'ancienne, laquelle reste consultable.

Une version soumise ou approuvée est immuable dans les services. Une évolution
crée une nouvelle version et invalide immédiatement l'ancienne pour l'usage.

## `equipment_approved_analytes`

Chaque ligne appartient à une version de qualification et contient :

- `analyte_code` ;
- `method_code` ;
- `sample_type` ;
- `unit` ;
- contexte et référence catalogue facultatifs ;
- indicateur `active` et version de métadonnées.

La combinaison qualification/analyte/méthode/type/unité est unique. Aucun seuil,
intervalle biologique, facteur de conversion, plage analytique ou règle
d'auto-validation n'est dupliqué ici. La migration ne crée aucune ligne.

## `equipment_documents`

La table contient uniquement titre, type, fabricant/modèle/version, langue,
date, pages, disponibilité, référence externe, présence de sections,
statut/relecteur/date et checksum. Elle ne contient ni manuel intégral, ni scan,
ni donnée patient, ni secret.

Une métadonnée déjà référencée par une qualification soumise devient immuable.
Une nouvelle preuve est un nouvel enregistrement lié à une nouvelle version.

## Index et intégrité

- unicité de `asset_identifier` et `stable_identifier` ;
- index sur les FK et `equipments.unit` ;
- FK `RESTRICT` : aucun historique qualifié n'est supprimé en cascade ;
- aucun endpoint de hard delete pour interfaces, qualifications ou documents ;
- audits applicatifs atomiques ; durcissement SQL de l'immutabilité restant à
  décider avec le DBA.
