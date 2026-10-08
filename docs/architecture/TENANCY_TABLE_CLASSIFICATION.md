# Classification de tenancy de 100 % des tables

Base : `origin/main` = `b40021ca91abf49f46da5bc762506b7786fd863e`, Alembic head
`20260826_0043`, **49 tables** dans `Base.metadata` (la table technique
`alembic_version` est hors métadonnée et hors périmètre).

Cette table est **contrôlée par un test** (`tests/test_tenancy_table_classification.py`) :
toute table présente dans `Base.metadata` et absente ici fait échouer la suite,
de même qu'une ligne de ce document qui ne correspond plus à aucune table, ou
une portée hors de la liste autorisée. Ne modifier le format des lignes de la
section « Classification » qu'en modifiant le test.

Scopes autorisés : `GLOBAL`, `TENANT`, `SITE`, `UNIT`, `TECHNICAL`, `TBD`.

* `GLOBAL` — référentiel partagé par tous les tenants, lecture pour tous, écriture plate-forme uniquement.
* `TENANT` — appartient à un tenant ; `tenant_id NOT NULL` ; RLS.
* `SITE` — appartient à un site d'un tenant ; `tenant_id` + `site_id NOT NULL` ; RLS sur `tenant_id`.
* `UNIT` — appartient à une unité organisationnelle (`org_unit_id`) ; aucune table n'est classée UNIT en première intention : l'unité est un **attribut d'autorisation** porté par des tables SITE/TENANT (`patients`, `equipments`), pas une frontière de propriété.
* `TECHNICAL` — infrastructure (jetons, état d'intégration) ; pas de donnée métier de tenant.

Légende colonnes : **T/S/U req.** = `tenant_id` / `site_id` / `org_unit_id` requis à terme
(Y = NOT NULL, opt = nullable, N = non). **RLS** = candidate à une politique RLS.

## Synthèse

| Scope | Nombre |
|---|---|
| GLOBAL | 6 |
| TENANT | 14 |
| SITE | 24 |
| UNIT | 0 |
| TECHNICAL | 2 |
| TBD | 3 |
| **Total** | **49 / 49 = 100 %** |

## Classification

| Table | Business meaning | Scope | Parent | Tenant required | Site required | Unit required | RLS candidate | Current unique constraints | Required future change | Migration complexity | Risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `aes_incidents` | Accidents d'exposition au sang du personnel | SITE | sites | Y | Y | opt | Y | — | Ajouter tenant_id, site_id ; RLS | Low | High (santé du personnel) |
| `audit_events` | Journal d'audit append-only | TENANT | tenants | Y | opt | N | Y | — | tenant_id NOT NULL ; événements plate-forme dans un flux `platform_audit_events` séparé ; index (tenant_id, created_at) | High (volume, append-only) | Critical |
| `auto_validation_configs` | Règles d'autovalidation clinique | TENANT | tenants | Y | opt | N | Y | — | tenant_id ; activation par site à étudier | Medium | High (clinique) |
| `biological_code_mappings` | Correspondance de codes biologiques (référentiel) | GLOBAL | — | N | N | N | N | — | Écriture plate-forme seule ; surcharges tenant éventuelles dans une table distincte | Low | Medium |
| `biological_reference_ranges` | Référentiel bioref de valeurs usuelles | GLOBAL | — | N | N | N | N | — | Écriture plate-forme seule | Low | Medium |
| `bnpl_payments` | Échéances de paiement fractionné | TENANT | bnpl_schedules | Y | N | N | Y | — | tenant_id ; FK composite (tenant_id, schedule_id) | Medium | High (financier) |
| `bnpl_schedules` | Échéanciers de paiement fractionné | TENANT | tenants | Y | N | N | Y | — | tenant_id ; `patient_ref` texte sans FK à remplacer par FK composite vers patients | Medium | High (financier + patient) |
| `corrective_actions` | Actions correctives (CAPA) | TENANT | non_conformities | Y | opt | N | Y | — | tenant_id ; FK composite vers non_conformities | Low | Medium |
| `critical_ranges` | Seuils critiques par analyte | TBD | — | ? | N | N | ? | — | Voir TBD-1 | Low | High (clinique) |
| `csa_sync_state` | État singleton de la synchro CSA | TBD | — | ? | N | N | N | — | Voir TBD-3 | Low | Medium |
| `delta_check_rules` | Règles de delta-check par analyte | TENANT | tenants | Y | N | N | Y | (analyte) | UNIQUE (tenant_id, analyte) | Low | High (clinique) |
| `dh36_inbound_messages` | Messages HL7/DH36 bruts entrants des analyseurs | SITE | equipment_interfaces | Y | Y | N | Y | (raw_hash) ; (message_control_id) | UNIQUE (tenant_id, raw_hash), (tenant_id, message_control_id) ; tenant dérivé de l'interface réceptrice, jamais du message | High | Critical (porte PII) |
| `epi_notifications` | Déclarations épidémiologiques | SITE | patients | Y | Y | opt | Y | — | tenant_id, site_id ; FK composite vers patients | Medium | Critical |
| `equipment_approved_analytes` | Analytes approuvés par qualification d'équipement | SITE | equipment_qualifications | Y | Y | N | Y | (qualification_id, analyte_code, method_code, sample_type, unit) | Préfixer la contrainte par tenant_id ; `unit` = unité de mesure | Low | Medium |
| `equipment_documents` | Documentation des équipements | SITE | equipments | Y | Y | N | Y | — | tenant_id, site_id ; préfixe tenant de `storage_reference` | Low | Medium |
| `equipment_interfaces` | Interfaces de connexion des analyseurs | SITE | equipments | Y | Y | N | Y | (stable_identifier) | UNIQUE (tenant_id, stable_identifier) | Medium | High (routage des messages) |
| `equipment_maintenances` | Maintenances équipement | SITE | equipments | Y | Y | N | Y | — | tenant_id, site_id ; FK composite | Low | Low |
| `equipment_qualifications` | Qualifications équipement versionnées | SITE | equipments | Y | Y | N | Y | (equipment_id, version) ; (superseded_by_id) | Préfixer par tenant_id ; FK composite superseded_by | Medium | High |
| `equipment_reagent_ratio_versions` | Historique des ratios équipement/réactif | SITE | equipment_reagent_ratios | Y | Y | N | Y | — | tenant_id, site_id ; FK composite | Low | Low |
| `equipment_reagent_ratios` | Consommation réactif par équipement | SITE | equipments | Y | Y | N | Y | — | tenant_id, site_id ; FK composites vers equipments et reagents | Low | Low |
| `equipments` | Parc d'analyseurs | SITE | sites | Y | Y | opt | Y | (serial_number) ; uidx (asset_identifier) | UNIQUE (tenant_id, serial_number), (tenant_id, asset_identifier) ; `unit` organisationnelle → org_unit_id | Medium | High |
| `exam_order_items` | Lignes de prescription | SITE | exam_orders | Y | Y | N | Y | — | tenant_id, site_id ; FK composites | Medium | High |
| `exam_orders` | Prescriptions d'examens | SITE | patients | Y | Y | opt | Y | (csa_prescription_id) | UNIQUE (tenant_id, csa_prescription_id) | High | Critical |
| `exam_tariffs` | Tarifs des examens (XOF) | TENANT | tenants | Y | N | N | Y | (exam_code) | UNIQUE (tenant_id, exam_code) | Low | Low (non clinique) |
| `invoice_lines` | Lignes de facture | TENANT | invoices | Y | opt | N | Y | — | tenant_id ; FK composite | Medium | High |
| `invoice_payments` | Encaissements | TENANT | invoices | Y | opt | N | Y | — | tenant_id ; FK composite | Medium | High |
| `invoices` | Factures | TENANT | tenants | Y | opt | N | Y | (invoice_number) | UNIQUE (tenant_id, invoice_number) ; séquence de numérotation par tenant | High | Critical (légal + patient) |
| `malaria_analysis_jobs` | Jobs d'analyse IA paludisme | SITE | results | Y | Y | N | Y | — | tenant_id dans la charge utile du job ; préfixe tenant de `image_url` | Medium | High (fichiers) |
| `military_facilities` | Référentiel géographique des formations militaires | GLOBAL | — | N | N | N | N | — | Écriture plate-forme seule ; **ne pas l'utiliser comme table de tenants ni de sites** | Low | Low |
| `non_conformities` | Non-conformités qualité | TENANT | tenants | Y | opt | N | Y | — | tenant_id ; `linked_entity_id` polymorphe à valider dans le tenant | Medium | Medium |
| `notif_configs` | Configuration de notification (webhook, email) | TENANT | tenants | Y | opt | N | Y | — | tenant_id ; destinations validées par tenant | Low | High (exfiltration) |
| `patients` | Dossiers patient | TENANT | tenants | Y | opt | opt | Y | (ipp_unique_id) | UNIQUE (tenant_id, ipp_unique_id) ; `unit` → org_unit_id ; suppression du pool `unit IS NULL` | High | Critical |
| `qc_controls` | Contrôles qualité définis | SITE | sites | Y | Y | N | Y | — | tenant_id, site_id | Low | Medium |
| `qc_results` | Résultats de contrôle qualité | SITE | qc_controls | Y | Y | N | Y | — | tenant_id, site_id ; FK composite | Low | Medium |
| `ratio_preset_items` | Lignes de modèles de ratios | GLOBAL | ratio_presets | N | N | N | N | — | Suit son parent | Low | Low |
| `ratio_presets` | Modèles de ratios équipement/réactif | GLOBAL | — | N | N | N | N | (name) | Modèles plate-forme ; un tenant qui personnalise copie vers equipment_reagent_ratios | Low | Low |
| `reagent_lots` | Lots de réactifs reçus | SITE | reagents | Y | Y | N | Y | — | tenant_id, site_id ; FK composite | Medium | Medium |
| `reagents` | Réactifs et stock courant | SITE | sites | Y | Y | N | Y | (name) | UNIQUE (tenant_id, site_id, name) ; séparer catalogue et stock à terme | Medium | Medium |
| `reference_ranges` | Valeurs de référence locales | TBD | — | ? | N | N | ? | — | Voir TBD-2 | Low | High (clinique) |
| `refresh_tokens` | Jetons de rafraîchissement | TECHNICAL | users | N | N | N | N | (token_hash) | Option : lier le jeton au membership sélectionné | Low | High (auth) |
| `report_delivery_outbox` | Outbox de diffusion des comptes rendus | SITE | report_snapshots | Y | Y | N | Y | (idempotency_key) | tenant_id ; UNIQUE (tenant_id, idempotency_key) ; worker par tenant | Medium | Critical |
| `report_signatures` | Signatures des comptes rendus | SITE | results | Y | Y | N | Y | (result_id) | UNIQUE (tenant_id, result_id) ; FK composite | Medium | Critical |
| `report_snapshots` | Instantanés immuables de comptes rendus | SITE | results | Y | Y | N | Y | (verification_token_hash) ; (result_id, version_number) | Garder verification_token_hash globalement unique (lookup public), résolution par fonction `SECURITY DEFINER` à sortie minimale | High | Critical |
| `results` | Résultats d'analyses | SITE | samples | Y | Y | N | Y | — | tenant_id, site_id ; FK composites vers samples et equipments | High | Critical |
| `revoked_tokens` | Liste de révocation JWT | TECHNICAL | users | N | N | N | N | (jti) | Aucun | Low | High (auth) |
| `samples` | Échantillons | SITE | patients | Y | Y | N | Y | (barcode) | UNIQUE (tenant_id, barcode) ; numéro de laboratoire par (tenant, site) | High | Critical |
| `stock_movements` | Mouvements de stock | SITE | reagents | Y | Y | N | Y | — | tenant_id, site_id ; FK composites | Medium | Medium |
| `tat_targets` | Objectifs de délai de rendu (TAT) | TENANT | tenants | Y | N | N | Y | (exam_code) | UNIQUE (tenant_id, exam_code) | Low | Low (non clinique) |
| `users` | Identités authentifiables | GLOBAL | — | N | N | N | N | (username) | Devient `UserIdentity` plate-forme ; `role` et `unit` migrent vers `tenant_memberships` ; username reste globalement unique | High | Critical (auth) |

## TBD

| ID | Table | Reason | Decision owner | Blocking question |
|---|---|---|---|---|
| TBD-1 | `critical_ranges` | Les seuils critiques sont une politique clinique ; ils peuvent être imposés par un référentiel national (GLOBAL) ou propres à chaque laboratoire (TENANT), voire à chaque site/automate | Biologiste responsable / responsable qualité | Les seuils critiques peuvent-ils différer entre deux tenants ? Si oui : TENANT avec valeurs par défaut GLOBAL copiées à la création du tenant. |
| TBD-2 | `reference_ranges` | Coexiste avec `biological_reference_ranges` (GLOBAL) ; son rôle (surcharge locale vs doublon historique) n'est pas documenté | Biologiste responsable | `reference_ranges` est-elle la surcharge locale d'un laboratoire ? Si oui : TENANT (ou SITE si dépendante de la méthode/automate). |
| TBD-3 | `csa_sync_state` | Singleton (`id` unique) de l'état d'une intégration CSA par instance | Responsable intégration CSA | Chaque tenant a-t-il sa propre connexion CSA ? Si oui : TENANT, une ligne par (tenant, intégration) ; sinon : TECHNICAL plate-forme. |

## Tables futures (non créées dans ce lot)

`tenants` (GLOBAL/plate-forme), `sites` (TENANT), `org_units` (SITE),
`tenant_memberships` (TENANT, lien vers `users`), `platform_audit_events`
(TECHNICAL plate-forme). Elles devront être ajoutées à cette classification
dans le lot qui les crée — le test l'impose.
