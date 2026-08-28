# Changelog

Toutes les évolutions notables de RuggyLab OS sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Non publié]

## [0.8.0-beta.1] - 2026-08-28

> ⚠️ **BÊTA TECHNIQUE — `REAL_DATA_NO_GO`.** Version destinée au développement,
> à la qualification technique et aux essais sur données fictives ou
> synthétiques. Elle ne constitue **pas** une autorisation d'utilisation
> clinique réelle. La synchronisation CSA et les interfaces automates restent
> désactivées par défaut.

Première version consolidée depuis `v0.7.4` (2026-06-18) : 173 commits,
283 fichiers, 14 migrations. Le détail fonctionnel est repris dans la section
« Non publié » ci-dessus, conservée telle quelle ; cette section en résume la
portée, les limites et la conduite à tenir.

### Sécurité

- **SSRF authentifiée des webhooks sortants fermée** (PR #133). Transport HTTP
  sortant centralisé : toutes les réponses DNS validées puis socket épinglé sur
  l'adresse vérifiée (aucun rebinding), rejet des adresses non globales en IPv4
  et IPv6 y compris IPv4-mapped, userinfo refusé, redirections jamais suivies,
  SNI et en-tête `Host` préservés, **plancher TLS 1.2**.
- **Cohérence patient au point de publication externe** : le flux sortant CSA
  revérifie, avant tout envoi, que l'échantillon d'où provient le résultat
  appartient bien au patient de l'ordre. Fail-closed.
- **Journaux sans identifiant corrélable à un patient** : ni donnée nominative,
  ni `patient_id`, ni `csa_prescription_id`, ni âge exact.
- **Réponses d'erreur sans détail interne** : les sondes de santé n'exposent
  plus les coordonnées de la base ; un identifiant d'incident remplace la trace,
  conservée côté serveur.
- **Ports automates** : la stack de base n'en publie aucun ; leur ouverture
  passe par un override explicite borné à une interface nommée, avec refus au
  démarrage d'un bind universel ou d'une adresse publique.
- **Pipeline de release verrouillé** : la GitHub Release ne peut plus précéder
  les tests, et une pré-version ne peut plus se présenter comme stable.

### Ajouté

- Intégration **CSA Plateau ↔ RuggyLab** : flux entrant prescriptions → ordres
  (I1), flux sortant résultats → CSA (I2), observabilité et runbook de bascule
  (I4). **Inactive par défaut.**
- File de travail : les ordres d'examen, dont ceux d'origine CSA, sont surfacés
  dans « Ma file ».
- Registre normalisé des équipements et qualifications.
- Vérification de restauration PostgreSQL exécutée en intégration continue.

### Migrations

14 migrations, de `20260618_0029` à `20260826_0043`. Tête unique
`20260826_0043`. Cycle `downgrade base` → `upgrade head` vérifié en CI, ainsi
que la restauration d'une sauvegarde `pg_dump` dans une base vierge.

### Configuration

35 nouvelles variables. Les plus structurantes, **toutes fail-closed par
défaut** : `CSA_SYNC_ENABLED=false`, `ANALYZER_BIND_IP=127.0.0.1`,
`ENABLE_DH36_LISTENER=false`, `ANALYZER_RAW_LISTENER_ENABLED=false`.
`.env.example` ne contient plus aucune clé de projet concrète.

### Limites connues

- **`REQUIRE_VALIDATION_FOR_RELEASE=false`** reste admis : un résultat peut être
  libéré sans validation biologique. Ce n'est pas une validation, et le contrat
  CSA le dit désormais explicitement (`libere_sans_validation`).
- **6 alertes CodeQL hautes** restent ouvertes, toutes analysées et justifiées
  dans `docs/security/CODEQL_HIGH_TRIAGE_2026-08-27.md`.
- **Aucun automate physique qualifié.** Les interfaces restent inertes.
- Le compte technique CSA est **sur-privilégié côté `csa-plateau`** ; la
  correction est préparée mais non déployée. `CSA_SYNC_ENABLED` doit rester
  `false`.
- **Composants tiers non entièrement qualifiés** — **bloquant pour toute
  distribution externe.** Deux composants sont en revue de licence obligatoire :
  **Redis 7.4** (source-available RSALv2/SSPLv1 depuis cette version, et non
  plus BSD-3-Clause) et **Grafana 11** (AGPL-3.0, dont les obligations diffèrent
  selon que la pile est seulement déployée ou réellement distribuée). Le SBOM de
  l'image a fait apparaître un troisième point : la base `python:3.13-slim`
  embarque **87 paquets Debian, majoritairement sous GPL/LGPL**. Les notices et
  les textes de licence sont bien présents dans l'image — vérifié —, mais
  l'obligation d'**offre du code source** attachée à la distribution de binaires
  GPL n'a pas été instruite. Cela ne rend pas RUGGYLAB OS open source. La police
  chargée depuis Google Fonts reste à préciser. Options et détail dans
  `THIRD_PARTY_NOTICES.md` §6.

### Licence

La déclaration GPL-2.0 antérieure était **inexacte** : elle figurait dans
`pyproject.toml`, le `Dockerfile` et le README alors que le dépôt ne contenait
**aucun fichier `LICENSE`**.

**Décision de principe adoptée.** RUGGYLAB OS `0.8.0-beta.1` est publié sous
**RuggyLab Evaluation License 1.0** (`LicenseRef-RuggyLab-Evaluation-1.0`),
licence propriétaire d'évaluation. Copyright © 2026 WOGNIN Nelson Rommell Boni
Ruggairrhye. Les quatre déclarations du dépôt sont alignées et verrouillées par
un test.

Deux réserves, explicites :

- **le texte n'a pas été validé par un juriste.** Les clauses de droit
  applicable, juridiction, durée, limitation de responsabilité et règlement des
  litiges sont regroupées au §12 de `LICENSE.md` et **exigent cette validation
  avant toute distribution externe** ;
- **les obligations des composants tiers ne sont pas toutes satisfaites** à ce
  jour (voir ci-dessus). La qualification des composants tiers appartient au
  gate de **distribution**, pas au gate de build.

`THIRD_PARTY_NOTICES.md` recense les composants, leurs licences et leurs
obligations ; les textes intégraux sont dans `licenses/third-party/`. Les
distributions Python et l'image Docker les embarquent.

### Gouvernance de la distribution

Décisions du titulaire, arrêtées le 2026-08-28 :

- **durée d'évaluation : six mois maximum**, sans reconduction tacite ; toute
  prolongation exige une autorisation écrite distincte. Cinq cas de cessation
  anticipée sont énumérés (`LICENSE.md` §4.1 et §4.2). La durée n'est donc plus
  au nombre des clauses en attente de validation juridique ;
- **Redis 7.4 écarté de la distribution**, remplacement prévu par **Valkey**
  (BSD-3-Clause) ;
- **Grafana hors du cœur distribué** : intégration optionnelle et externe,
  récupérée par l'exploitant auprès de son éditeur. **Prometheus est conservé**
  dans la stack principale, et l'absence de Grafana n'est pas un mode dégradé ;
- **dépôt privé avant tag** — préparation seulement, la visibilité est
  inchangée.

Une décision n'est pas une mise en œuvre : `REDIS_REPLACED_BY_VALKEY` et
`GRAFANA_EXTERNALIZED` ne sont **pas** prononcés, et les marqueurs de revue
obligatoire restent en place tant que les PR techniques ne sont pas fusionnées.

Modèle d'autorisation d'évaluation pour le site du CSA GR Plateau : préparé,
**non signé**. Le site est un site d'évaluation et ne détient aucun droit de
propriété.

### Rollback

Revenir au tag `v0.7.4`, ou déployer l'image du digest précédent. Aucune
migration de cette version n'est destructrice ; `alembic downgrade` jusqu'à
`20260625_0036` restitue l'état antérieur. Désactiver l'intégration se fait par
`CSA_SYNC_ENABLED=false`, qui est déjà le défaut.


### Ajouté
- **Workflow valeurs critiques** : prise en charge depuis la liste résultats,
  audit clinique ouvrable depuis une ligne, confirmation groupée avec contexte
  patient/échantillon, rapport conformité avec seuil cible, indicateur hors
  délai, agent de prise en charge, filtres examen/unité, synthèse qualité et
  export CSV.
- **Dashboard Qualité laboratoire** : vue consolidée valeurs critiques, TAT,
  QC analytique et NC/CAPA pour prioriser les actions qualité.
- **Unification des vocabulaires biologiques** : table de correspondance
  canonique `biological_code_mappings` reliant `exam_code` ↔ `test_code` ↔
  `analyte` (panels NFS/IONO inclus) et interprétation bioref complémentaire
  des résultats (sans modifier le moteur de flags existant).
- **Référentiel biologique** (IFCC/Tietz/OMS) : valeurs de référence par
  sexe/âge, seuils critiques, interprétation (NORMAL/BAS/HAUT/CRITIQUE).
- **Suivi TAT** (Turnaround Time) : horodatages de phase, cibles par examen,
  tableau de bord et alertes de dépassement.
- **Registre maître** : prévisualisation, import (dry-run + confirmation) et
  analyse rétrospective (recettes, CMU, paludisme).
- **Catalogue d'examens** et parseur de texte libre (registre papier).
- **Module qualité** NC/CAPA, conformité avancée, notifications temps-réel
  (WebSocket + fan-out Redis), import en lot, RBAC dossiers patient.

### Sécurité
- Durcissement : anti-SSRF des webhooks, neutralisation d'injection CSV,
  RBAC sur l'amendement de résultats, révocation des jetons d'accès (denylist
  JTI), traçabilité d'accès aux dossiers patient.

### Infrastructure
- CI consolidée (lint/format en gate dur, sécurité en advisory), tests
  PostgreSQL des migrations, CodeQL, publication d'image Docker sur tag.
