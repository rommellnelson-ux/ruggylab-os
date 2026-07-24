# DÉCISION ÉQUIPEMENT — registre d'homologation

## Appareils concernés

Tous les équipements analytiques et POCT ; en priorité DH36, Dymind biochimie,
coagulation, BIOSCANN CHEM 100 et Precix/ProCheck Expert.

## Question

Faut-il étendre le modèle `Equipment` pour rendre l'activation d'une interface
explicitement dépendante d'une identité, d'un protocole, d'un périmètre clinique
et d'une qualification versionnés ?

## Preuve

`app.models.ruggylab_os.Equipment` ne contient actuellement que `id`, `name`,
`serial_number`, `type`, `location` et `last_calibration`. Il ne peut pas porter
de façon vérifiable fabricant, modèle, firmware, protocole, driver,
qualification, analytes, unités, méthodes, site, état d'activation ou version
de configuration.

Le code a donc été mis en sécurité sans migration : interfaces désactivées,
POCT refusé et drivers inconnus maintenus en stubs. Cette protection ne permet
pas d'homologuer puis d'activer proprement un appareil.

## Option A — colonnes additives sur `equipments`

Ajouter les champs d'identité, connectivité et état directement à la table :
`manufacturer`, `model`, `device_family`, `firmware_version`, `clinical_use`,
`connection_type`, `connection_endpoint`, `protocol_name`,
`protocol_version`, `driver_name`, `driver_version`,
`qualification_status`, `enabled`, `qualification_date`, `qualified_by` et
`configuration_version`. Les méthodes/analytes/unités resteraient en JSON
versionné.

- Coût relatif : moyen.
- Avantage : migration et lecture simples.
- Risque : historique, multiprotocoles, documents et révisions difficiles à
  auditer ; JSON clinique moins contraint.

## Option B — identité additive et sous-registres normalisés

Ajouter sur `equipments` l'identité stable (`manufacturer`, `model`,
`device_family`, `firmware_version`, site et statut global), puis créer :

- `equipment_interfaces` : type, endpoint expurgé, protocole/driver/version,
  direction, activation et version de configuration ;
- `equipment_qualifications` : statut, périmètre clinique, dates, approbateur,
  preuve et version immuable ;
- `equipment_approved_analytes` : méthode, analyte, unité et contraintes
  approuvées ;
- `equipment_documents` : métadonnées documentaires sans manuel intégral.

- Coût relatif : élevé.
- Avantage : séparation des responsabilités, historique, multi-interface,
  contraintes et preuve d'homologation.
- Risque : davantage de tables, API, RBAC, tests et gouvernance.

## Recommandation

**Option B**, en migration additive et par étapes. Elle correspond mieux à une
traçabilité médicale et empêche qu'un booléen isolé active un profil incomplet.

## Reprise des données

- Conserver tous les enregistrements existants.
- Ne fabriquer aucune marque, modèle, méthode, unité ou qualification.
- Initialiser les nouveaux champs inconnus à `NULL`.
- Initialiser toute interface à `enabled=false` et toute qualification à
  `unqualified`.
- Masquer les numéros de série dans les exports et documents.
- Exiger une revue humaine appareil par appareil avant enrichissement.

## Autorisation exacte attendue

Autoriser ou refuser la conception détaillée puis l'implémentation d'une
migration additive selon :

- **A** — colonnes principalement intégrées à `equipments` ;
- **B** — identité additive et sous-registres normalisés, recommandée.

Aucune migration n'est incluse dans le présent dossier.
