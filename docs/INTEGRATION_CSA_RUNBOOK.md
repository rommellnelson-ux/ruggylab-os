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

### 1.1 Garde-fous de sécurité clinique du flux sortant

Le flux sortant publie un résultat **sous une identité patient, chez un tiers**.
Deux garde-fous non contournables encadrent cette publication.

**a) Cohérence patient (fail-closed).** Avant toute publication, `_same_patient()`
revérifie que l'échantillon d'où provient le résultat appartient bien au patient
de l'ordre. L'API de rattachement le vérifie déjà, mais le flux sortant ne
dépend d'aucune garantie posée en amont : échantillon absent, orphelin ou
appartenant à un autre patient ⇒ **publication bloquée**, incident journalisé
(`csa_sync.outbound.patient_mismatch`, identifiants techniques uniquement).

**b) Niveau de validation annoncé sans ambiguïté.** Tant que
`REQUIRE_VALIDATION_FOR_RELEASE=False` est admis (mode dégradé), un résultat peut
être *libéré* sans validation biologique. Le payload `labo_resultats` distingue
donc explicitement les trois états — il ne présente jamais une libération en mode
dégradé comme une validation biologique :

| `statut` | `validation.niveau` | `mode_degrade` | Signification |
| --- | --- | --- | --- |
| `valide` | `biologique` | `false` | Validation biologique humaine |
| `valide_auto` | `auto` | `false` | Auto-validation par règles |
| `libere_sans_validation` | `aucune` | `true` | **Libéré sans validation** — mode dégradé |

Le bloc `validation` porte aussi `bio_validated_at`, `tech_validated_at`,
`auto_validated_at`, `released_at` et `valide_par_id`, afin que le prescripteur
CSA dispose de la traçabilité complète.

> **Contrat d'interface.** Les valeurs `valide_auto` et `libere_sans_validation`
> sont nouvelles : le consommateur CSA doit les prendre en charge avant la
> bascule. Un consommateur qui ne teste que `statut === 'valide'` cessera
> simplement d'afficher les résultats non validés — dégradation sûre, mais à
> valider explicitement avec l'équipe CSA.

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

Prérequis base : `alembic upgrade head` (migrations `20260826_0041` →
`20260826_0043`).

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
> **complétude du workflow opérateur RuggyLab comprise (cf. §8)**, personnel prêt
> à consulter les résultats dans CSA, procédure de repli comprise.

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
  santé — 21 tests) + `tests/test_worklist.py` (ordres CSA dans la file).
- CSA : `tests.html` (formatage + lien accusés/résultats — TESTS_PASS).
- End-to-end staging : cf. `scripts/csa_sync_smoke.py` (entrant) et
  `scripts/csa_sync_outbound_smoke.py` (sortant), base SQLite jetable.

---

## 8. Complétude du workflow opérateur RuggyLab (audit 2026-08-26)

L'intégration remonte les résultats **validés** ; encore faut-il qu'un opérateur
puisse, dans RuggyLab, faire cheminer un ordre reçu de CSA jusqu'à un résultat
validé. Audit du parcours (ordre → prélèvement → résultat → validation) :

| Étape | État | Détail |
|---|---|---|
| Voir l'ordre CSA | ✅ **corrigé** | Les ordres `prescribed`/`collected` (origine CSA distinguée) apparaissent dans « Ma file » (`_exam_order_items`, `app/services/worklist.py`). |
| Prélever (rattacher échantillon) | ✅ existe | `POST /exam-orders/{id}/collect` → `ExamOrder.sample_id` ; transition auto `prescribed→collected`. |
| Saisir un résultat | ⚠️ partiel | Fonctionne (`sample_id`+`exam_code`), mais `ExamOrderItem.result_id` n'est réconcilié que paresseusement (`sync_order_progress`, à l'ouverture du fil). |
| Valider / libérer | ⚠️ partiel | Le résultat naît `is_validated=True` (pas de double contrôle bio) ; `released_at` jamais posé. |

**Verdict** : le parcours est fonctionnel et désormais **surfacé** dans la file de
travail. Deux limites subsistent, qui sont des **choix**, pas des bugs :

- **Lien ordre↔résultat paresseux** (trou n°2). Sans impact sur l'intégration : le
  flux sortant fait sa **propre réconciliation** par échantillon
  (`Result.sample_id == ExamOrder.sample_id`), indépendamment de
  `ExamOrderItem.result_id`.
- **Validation implicite** (trou n°3). Décision de gouvernance assumée
  (`REQUIRE_VALIDATION_FOR_RELEASE=false`, faute de biologiste validateur). **À
  traiter le jour où ce personnel arrive** : basculer le flag à `true` (validation
  stricte avant libération) et ajouter une étape de bio-validation explicite reliée
  à l'`ExamOrder`, en renseignant `released_at`. Voir la section RESULT REPORT
  RELEASE POLICY de `.env.example` et `docs/ARCHITECTURE_AS_BUILT.md §11`.

Prérequis de mise en service : ces deux points sont acceptables pour un démarrage
en **mode dégradé** (un seul manipulateur, pas de biologiste). Ils ne bloquent ni
l'intégration ni le parcours opérateur.
