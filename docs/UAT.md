# Guide de tests utilisateurs (UAT) — RuggyLab OS

Ce guide permet à un testeur métier de valider RuggyLab OS sur une **instance de
test dédiée** (jamais la production). Données patients réelles → instance
cloisonnée, comptes nominatifs, audit activé.

## 1. Démarrer une instance de test

```bash
# Variables d'environnement (valeurs de test)
export SECRET_KEY="ruggylab-uat-secret-key-min-32-characters"
export FIRST_SUPERUSER_PASSWORD="SuperAdmin2026!SecurePass"   # ≥ 16 caractères
export DATABASE_URL="postgresql+psycopg://ruggylab:motdepasse@localhost:5432/ruggylab_uat"
# (ou SQLite pour un essai rapide : sqlite:///./uat.db)

alembic upgrade head                       # crée le schéma
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Cockpit : http://127.0.0.1:8000/app · Doc API : http://127.0.0.1:8000/docs

## 2. Amorcer les référentiels + jeu de démonstration (recommandé)

Le plus simple — un seul script charge les référentiels **et** un jeu de données
fictif (12 dossiers importés depuis un registre synthétique + 4 résultats riches
avec valeurs critiques, paludisme positif et horodatages TAT) :

```bash
python -m scripts.seed_demo
```

Résultat attendu : ~16 patients, ~33 résultats, 65 valeurs de référence, 23 cibles
TAT, 31 correspondances de codes — les testeurs ont de la matière dès la connexion.

Alternative manuelle (référentiels seuls, sans données patient), via l'API admin :

| Référentiel | Endpoint |
|---|---|
| Valeurs de référence biologiques (65) | `POST /api/v1/bioref/seed-defaults` |
| Cibles TAT par examen | `POST /api/v1/tat/targets/seed-defaults` |
| Correspondances de codes (unification) | `POST /api/v1/code-mappings/seed-defaults` |
| Règle d'auto-validation §5.8 | `POST /api/v1/auto-validation/config` |

## 3. Créer les comptes par rôle (pour tester le RBAC)

Via `POST /api/v1/users` (admin) :
- **admin** — déjà présent (accès total).
- **officer** — `{"username":"biologiste","password":"...","role":"officer"}`.
- **technician** — `{"username":"tech_hema","password":"...","role":"technician","unit":"hematologie"}`.

## 4. Scénarios à valider

### A. Cycle de vie d'un résultat
1. Créer un patient → un échantillon → un résultat (vue Résultats du cockpit).
2. Vérifier : flags HH/H/N/L/LL, détection critique, delta-check, **auto-validation §5.8**.
3. Corriger un résultat (✏️) — réservé **officier** ; vérifier que la signature
   éventuelle est révoquée et qu'un événement d'audit est créé.

### B. Référentiel & interprétation
1. Vue Résultats → panneau « 📚 Référentiel biologique ».
2. Interpréter : `HB`, ♂, 12,4 → **BAS / 13-17 g/dL** ; `K` 7,0 → **CRITIQUE HAUT**.
3. Test qualitatif : goutte épaisse positive → **POSITIF (anormal)**.

### C. Unification des codes
1. Créer un résultat `exam_code="GE"` avec `{"MAL_GE":"positive"}` → champ
   `bioref_status` = **POSITIF (anormal)** (le code GE est relié à MAL_GE).
2. Panel `NFS` → interprétation **par composant** (Hb, Ht, WBC, PLT…).

### D. Suivi TAT (Performance labo)
1. Vue « ⏱️ Suivi TAT » : saisir les phases d'un résultat.
2. Vérifier le statut couleur (vert/orange/rouge), le tableau de bord et les alertes.

### E. Registre maître
1. Vue « 📚 Registre & Import » : coller un CSV, **Analyser** (recettes, CMU, paludisme).
2. **Prévisualiser** (dry-run) puis **Importer** (confirmation requise).

### F. Transverse
- Qualité NC/CAPA (déclaration → workflow → clôture).
- Notifications temps-réel (cloche topbar, toast valeur critique).
- Conformité ISO 15189 (tuile dashboard, export).
- Audit : filtres + export CSV (admin).
- RBAC dossiers patient : un technicien d'une unité ne voit pas les dossiers
  d'une autre unité (accès refusé + tracé).

## 5. Points connus (non bloquants)
- Les étapes CI `pip-audit` / `detect-secrets` sont **informatives** (état externe).
- Tests Playwright (e2e) ignorés si Playwright n'est pas installé.
- Toute donnée patient saisie en UAT reste sur l'instance de test.

## 6. Remonter une anomalie
Indiquer : le scénario (A–F), l'action, le résultat attendu vs obtenu, le rôle
utilisé, et l'horodatage (pour corrélation avec le journal d'audit).
