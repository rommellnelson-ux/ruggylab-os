# Runbook — Intégration CSA Plateau ↔ RuggyLab OS (laboratoire)

Procédure d'exploitation du flux bidirectionnel entre **CSA Plateau** (PWA/Supabase,
prescription) et **RuggyLab OS** (LIMS, exécution). Statut au 2026-08-26 :
**I0→I3 livrés et validés end-to-end en staging**. Ce document couvre l'activation,
le monitoring, la curation, la rotation des identifiants et la **bascule production**.

---

## 1. Architecture (rappel)

- **Sens entrant** (CSA → RuggyLab) : prescription labo → `labo_prescriptions` →
  le worker RuggyLab *poll* (RPC `csa_ruggylab_pull_prescriptions`) → crée un
  `ExamOrder` + items mappés → accuse réception (`labo_receipts`).
- **Sens sortant** (RuggyLab → CSA) : résultat validé/libéré → `labo_resultats`
  (RPC `csa_ruggylab_push_event`) → affiché dans la consultation CSA (dossier
  clinique rapide).
- **Transport** : polling HTTP (PostgREST), compte technique `RUGGYLAB`, idempotent
  des deux côtés. Aucun couplage synchrone : si l'un tombe, le poll rattrape.
- **Garde-fou** : côté CSA, tout est *gated* par `LAB_INTEROP = (CSA_ENV==='staging')`.
  La **production reste inerte** tant que ce flag n'y est pas activé.

Composants RuggyLab : `app/services/csa_sync/` (`client.py`, `inbound.py`,
`outbound.py`, `exam_map.py`, `health.py`). Worker dans le process
`PROCESS_ROLE=scheduler` (`app/scheduler.py`), gated `CSA_SYNC_ENABLED`.

---

## 2. Configuration (variables d'environnement RuggyLab)

| Variable | Rôle | Staging |
|---|---|---|
| `CSA_SYNC_ENABLED` | Active le worker (sinon aucun appel réseau) | `true` pour activer |
| `CSA_SUPABASE_URL` | URL du projet Supabase CSA | `https://mzfrcoqjbizhgppwmjon.supabase.co` |
| `CSA_SUPABASE_ANON_KEY` | Clé *publishable* | `sb_publishable_dgEqnrHvaA5QObM588KHsw_cN9JkUe_` |
| `CSA_RUGGYLAB_EMAIL` | Compte technique | `ruggylab@csa.local` |
| `CSA_RUGGYLAB_PASSWORD` | **Secret** — via secret manager, jamais commité | *(fourni au déploiement)* |
| `CSA_SYNC_INTERVAL_SECONDS` | Cadence du poll | `60` |

Prérequis base : `alembic upgrade head` (migrations `20260709_0038` →
`20260711_0040`).

---

## 3. Monitoring

Script de statut (lecture seule, aucun appel réseau) :

```bash
python scripts/csa_sync_status.py           # texte
python scripts/csa_sync_status.py --json     # + export JSON
```

Il rapporte : dernier cycle entrant/sortant, watermark, compteurs, **file de
résultats en attente de remontée**, dernières erreurs, et la **liste des examens
non mappés à curer**. La logique est aussi exposée par `sync_health(db)`
(`app/services/csa_sync/health.py`) pour un endpoint d'admin ou un export métrique.

Signaux d'alerte :
- `dernière erreur` non vide côté entrant ou sortant → investiguer (identifiants,
  réseau, policies).
- `en attente` qui ne décroît pas alors que des résultats sont validés → vérifier
  que l'ordre a bien un **échantillon** (`sample_id`) et un `Result` au bon
  `exam_code`.

---

## 4. Curation des examens non mappés

Un examen CSA sans correspondance n'est **jamais perdu** : il arrive en
`ExamOrderItem.status='unmapped'` (code `CSA:<code>`), signalé par le statut.
Pour le prendre en charge :

1. `python scripts/csa_sync_status.py` → section « Examens NON MAPPÉS ».
2. Ajouter la correspondance dans `app/services/csa_sync/exam_map.py`
   (`CSA_TO_RUGGYLAB`), 1→N possible (ex. un bilan → plusieurs codes RuggyLab).
3. Vérifier que le code cible existe dans `app/services/exam_catalog.py`.
4. Les **nouvelles** prescriptions seront mappées ; les items déjà `unmapped` le
   restent (traçabilité) — les re-prescrire si besoin.

---

## 5. Rotation des identifiants RUGGYLAB

Le mot de passe du compte `ruggylab@csa.local` n'est **jamais** stocké en clair
dans le dépôt.

1. Réinitialiser le mot de passe du compte dans le **dashboard Supabase**
   (Authentication → Users) — action manuelle de l'administrateur.
2. Mettre à jour `CSA_RUGGYLAB_PASSWORD` dans le secret manager / l'environnement
   de l'instance RuggyLab.
3. Redémarrer le process `scheduler`. Le client se reconnecte au cycle suivant
   (refresh de jeton géré, re-login sur 401).

Aucune interruption fonctionnelle : le poll échoué est simplement rejoué.

---

## 6. Bascule PRODUCTION (décision de mise en service — À VALIDER)

> ⚠️ **Décision de release.** Ne pas exécuter sans validation explicite du
> responsable. Effectuer d'abord une revue : I0→I3 validés en staging (fait),
> personnel prêt à consulter les résultats dans CSA, procédure de repli comprise.

Projet prod CSA : `wsnehnempnexzxzuklbv`. Étapes :

1. **Compte technique** : créer le compte Auth `ruggylab@csa.local` dans la
   Supabase **prod** (dashboard) et confirmer l'email. *(Le mot de passe est posé
   par l'administrateur, jamais par un outil.)*
2. **Migration** : appliquer `supabase/migrations/202607010001_ruggylab_interoperability.sql`
   sur la prod. Elle est **agnostique du projet** (profil résolu par email,
   contrôles par `agent_code='RUGGYLAB'`) : aucune adaptation. Vérifier ensuite :
   profil `RUGGYLAB` actif, 2 RPC présentes, 3 policies présentes, RPC *fail-closed*
   sans identité.
3. **Front CSA** : activer l'interop en prod. Aujourd'hui
   `LAB_INTEROP = (CSA_ENV==='staging')` → **inerte en prod**. Le passage prod est
   donc un **choix explicite** (ex. flag serveur/liste blanche), à faire au moment
   décidé, pas par simple déploiement.
4. **RuggyLab prod** : pointer `CSA_SUPABASE_URL`/`ANON_KEY` sur la prod, poser
   `CSA_RUGGYLAB_PASSWORD` (secret manager), `CSA_SYNC_ENABLED=true`,
   `PROCESS_ROLE=scheduler` (ou `all`), `alembic upgrade head`.
5. **Vérification** : prescrire un examen réel → `scripts/csa_sync_status.py` doit
   montrer l'ordre intégré ; valider un résultat → vérifier son affichage dans la
   consultation CSA du patient.

### Repli (rollback)

- **Couper le flux** sans rien perdre : `CSA_SYNC_ENABLED=false` + redémarrer le
  scheduler. Les prescriptions restent en attente côté CSA, rejouées à la
  réactivation (watermark).
- **Désactiver l'affichage** côté CSA : repasser le flag `LAB_INTEROP` à faux.
- Les RPC/policies peuvent rester en place (inertes sans compte actif) ou être
  révoquées via un `revoke execute`.

---

## 7. Tests

- RuggyLab : `pytest tests/test_csa_sync*.py` (mapping, idempotence entrant/sortant,
  santé — 21 tests).
- CSA : `tests.html` (formatage + lien accusés/résultats — TESTS_PASS).
- End-to-end staging : cf. `scripts/csa_sync_smoke.py` (entrant) et
  `scripts/csa_sync_outbound_smoke.py` (sortant), base SQLite jetable.
