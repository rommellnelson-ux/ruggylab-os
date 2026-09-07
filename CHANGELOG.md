# Changelog

Toutes les évolutions notables de RuggyLab OS sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Non publié]

## [0.8.0-beta.1] — À PUBLIER

> **Cette version n'est pas publiée.** Aucun tag, aucune image, aucune Release
> n'existe. La date réelle sera inscrite au moment du tag ; y porter une date
> maintenant laisserait croire à une publication qui n'a pas eu lieu.

> ⚠️ **BÊTA TECHNIQUE — `REAL_DATA_NO_GO` et `DISTRIBUTION_NO_GO`.** Version
> destinée au développement, à la qualification technique et aux essais sur
> données fictives ou synthétiques. Elle ne constitue **pas** une autorisation
> d'utilisation clinique réelle, et **pas davantage** une autorisation de
> distribution. La synchronisation CSA et les interfaces automates restent
> désactivées par défaut.

Première version consolidée depuis `v0.7.4` (2026-06-18) : **195 commits**,
**334 fichiers**, **+49 812 / −6 557 lignes**, **14 migrations** jusqu'à la tête
unique `20260826_0043`. Le détail fonctionnel est repris dans la section
« Non publié » ci-dessus, conservée telle quelle ; cette section en résume la
portée, les limites et la conduite à tenir.

### Runtime et distribution

- **Valkey 8.1.9 remplace le serveur Redis 7.4.** Redis avait quitté
  BSD-3-Clause pour un double régime source-available restreignant la
  redistribution. Valkey est le fork BSD-3-Clause du même serveur, épinglé par
  digest. Le client `redis-py` (MIT), le protocole et le schéma `redis://` ne
  changent pas. Volume **neuf** : aucune compatibilité de format n'est affirmée
  sans test.
- **Grafana sort du cœur distribué.** Il devient une intégration optionnelle et
  externe (`docker-compose.monitoring.yml`), récupérée par l'exploitant auprès
  de son éditeur. **Prometheus reste dans le cœur** et collecte `/metrics`
  directement. Fonctionner sans Grafana n'est **pas un mode dégradé** : c'est le
  mode nominal supporté et testé.
- **Dépendance à Google Fonts supprimée.** L'interface utilise une pile de
  polices système ; aucune police n'est téléchargée ni embarquée.
- **Base Python épinglée** par version exacte et digest
  (`python:3.13.15-slim-trixie@sha256:7ce4b6df…`), dans les deux étapes du
  Dockerfile. Un tag flottant rendait la version non reproductible.
- **Image candidate construite une seule fois** et réutilisée par tous les jobs
  de qualification, puis publiée telle quelle : le SBOM, les preuves Debian et
  la qualification Docker portent sur l'artefact qui sera livré.

### Conformité

- **Licence propriétaire d'évaluation** — RuggyLab Evaluation License 1.0
  (`LicenseRef-RuggyLab-Evaluation-1.0`), durée de six mois sans reconduction
  tacite. Le texte est neutre à la visibilité du dépôt : accéder au code n'a
  jamais valu licence.
- **Preuves de source correspondante Debian** : 87 paquets binaires, 61 paquets
  sources, **194 fichiers sources** avec URL, taille et SHA-256 déclarés par
  Debian, tous vérifiés joignables. Terminologie non conclusive
  (`copyleft_detected`, `written_offer_applicability = LEGAL_REVIEW_REQUIRED`) :
  l'automatisation constate, elle ne qualifie pas juridiquement.
- **SBOM CycloneDX et SPDX**, inventaire Python, audit des licences d'image et
  registre d'exceptions, tous régénérés sur l'image candidate.
- **Deux gates bloquants pour la publication** : `license-compliance` et
  `debian-source-evidence`. `monitoring-overlay` reste hors des gates.

### Distribution — NO-GO

`DISTRIBUTION_STATUS = DISTRIBUTION_NO_GO`, distinct de `REAL_DATA_NO_GO`. Le
premier interdit de **remettre** le logiciel, le second de **soigner** avec.
`tag-guard` refuse tout tag, y compris une pré-version correctement formée, tant
que la distribution n'est pas autorisée. Le chemin `workflow_dispatch` de
`deploy` a été retiré : il permettait de publier sans tag, donc sans passer par
ce verrou.

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
- **Deux points de conformité restent ouverts**, et **aucun ne peut être fermé
  par du code** : la **forme de mise à disposition des sources correspondantes**
  de la base Debian (87 paquets, familles copyleft détectées ; notices et textes
  présents dans l'image, mais la forme de mise à disposition n'a pas été
  instruite), et la **validation juridique** des clauses du §12 de `LICENSE.md`.
  Les blocages Redis 7.4, Grafana et Google Fonts sont **fermés**. Détail dans
  `THIRD_PARTY_NOTICES.md` §6.
- **Protection de branche plus permissive que le pipeline** : 2 checks requis
  sur `main` contre 9 gates avant publication — voir
  `docs/governance/BRANCH_PROTECTION_PRE_TAG_REQUIRED_CHECKS.md`.
- **Dépôt encore public** alors que la décision est de le passer en privé avant
  le tag.

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
