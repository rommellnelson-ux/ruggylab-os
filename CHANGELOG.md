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
- **Licence non résolue** : GPL-2.0 est déclarée dans `pyproject.toml`, le
  `Dockerfile` et le README, mais le dépôt ne contient aucun fichier `LICENSE`.

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
