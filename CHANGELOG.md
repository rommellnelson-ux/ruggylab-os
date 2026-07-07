# Changelog

Toutes les évolutions notables de RuggyLab OS sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Non publié]

### Ajouté
- **Revue biologique différée** : les résultats conformes aux procédures
  techniques sortent immédiatement valides pour le patient, tout en alimentant
  une file interne priorisée. Les officiers et administrateurs peuvent solder
  cette revue individuellement ou en lot, avec horodatage et audit.
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
