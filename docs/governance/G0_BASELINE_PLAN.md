# G0 — Baseline : plan de fermeture

> **Ce document est un plan, pas une preuve.** Il définit les douze preuves à
> produire, comment chacune sera vérifiable, et ce qui la fait échouer.
> `G0_PASS` ne sera prononcé qu'après production **et revue** des douze.
>
> **Aucune fonctionnalité nouvelle n'est développée pour G0.** Le gate mesure
> et documente l'existant ; il ne le change pas — hors outillage de mesure et
> durcissements de CI explicitement listés.

| | |
| --- | --- |
| Gate | **G0 — Baseline** |
| Base | `main` @ `18bf868c1ffe599c591c3b55b9b4088b01d1336d` |
| Version | `0.8.0-beta.1` — non publiée |
| Statuts conservés | `REAL_DATA_NO_GO`, `DISTRIBUTION_NO_GO`, `CSA_SYNC_ENABLED=false`, listeners automates désactivés |

## Pourquoi une baseline, et pourquoi maintenant

Les cinq missions précédentes ont produit des preuves *ponctuelles* : licence,
notices, SBOM, sources Debian, identité de l'artefact. Elles répondent à « ce
qu'on distribue ». G0 répond à une autre question : **« qu'est-ce que ce
logiciel, mesuré ? »**

Sans cette mesure, toute affirmation ultérieure — couverture suffisante,
performance acceptable, permissions correctes — n'aurait rien à quoi se
comparer. Une baseline n'est utile que si elle est prise **avant** de changer
quoi que ce soit.

## Ce que le dépôt vaut aujourd'hui, mesuré

Ces chiffres sont le point de départ. Ils seront repris, affinés et vérifiés
par les preuves correspondantes.

| Mesure | Valeur relevée sur `18bf868` |
| --- | --- |
| Modules Python (`app/`) | **230** |
| Lignes de code (`app/`) | **~32 400** |
| Fichiers de test | **124** |
| Chemins d'API | **198** |
| Opérations d'API (GET/POST/PUT/PATCH/DELETE) | **231** |
| Tables déclarées | **49** |
| Migrations Alembic | **43** — tête unique `20260826_0043` |
| Rôles applicatifs | **4** — `TECHNICIAN`, `OFFICER`, `ADMIN`, `ACCOUNTANT` |
| Modules faisant des appels sortants | **14** |
| Couverture de tests | **non mesurée** — `pytest-cov` absent |

Deux constats orientent le plan : **la couverture n'est pas mesurable en
l'état**, et **le scan de secrets est en mode advisory** (`continue-on-error`),
donc non bloquant.

---

## Les douze preuves

Chaque preuve indique son **livrable**, sa **méthode**, son **critère
d'acceptation**, et ce qui la rend **fausse**. Une preuve produite à la main,
non reproductible, ne compte pas : ce qui n'est pas régénérable dérive.

### Lot A — Architecture et données

Branche : `g0/architecture-inventory`

#### 1. Inventaire architecture / API / données

- **Livrable** : `docs/g0/INVENTORY.md` + `artifacts/g0/inventory.json`
- **Méthode** : script `scripts/g0_inventory.py`, lisant le code — jamais une
  liste tenue à la main.
- **Acceptation** : le script tourne en CI et échoue si l'inventaire versionné
  diverge de ce qu'il regénère.
- **Faux si** : l'inventaire est écrit à la main ou n'est pas régénérable.

#### 2. C4 et architecture as-built

- **Livrable** : `docs/g0/C4.md` — niveaux Contexte, Conteneurs, Composants.
- **Méthode** : diagrammes Mermaid, versionnés en texte. `docs/ARCHITECTURE_AS_BUILT.md`
  existe déjà et sert de base ; il est complété, pas dupliqué.
- **Acceptation** : chaque conteneur du diagramme correspond à un service réel
  de `docker-compose.yml`, et réciproquement — vérifié par test.
- **Faux si** : le diagramme montre Grafana dans le cœur, ou un serveur Redis.

#### 3. Inventaire des routes

- **Livrable** : `artifacts/g0/routes.json` + tableau dans `docs/g0/ROUTES.md`
- **Méthode** : extraction depuis l'OpenAPI de l'application, pas depuis les
  décorateurs — c'est ce que l'application expose réellement qui compte.
- **Acceptation** : 198 chemins / 231 opérations recensés, chacun avec méthode,
  rôle requis, et exposition (publique / interne / bloquée au proxy).
- **Faux si** : une route existe sans être recensée, ou l'inverse.

#### 4. Schéma, tables, relations et migrations

- **Livrable** : `artifacts/g0/schema.json` + `docs/g0/SCHEMA.md`
- **Méthode** : introspection d'une base **PostgreSQL migrée**, pas des modèles
  Python — le schéma réel peut diverger des déclarations.
- **Acceptation** : 49 tables, leurs colonnes, clés étrangères, index et
  contraintes ; chaîne des 43 migrations avec tête unique vérifiée.
- **Faux si** : le schéma est décrit depuis les modèles sans passer par une
  base réellement migrée.

### Lot B — Sécurité et conformité des accès

Branche : `g0/security-baseline`

#### 5. Matrice rôles / permissions

- **Livrable** : `artifacts/g0/rbac-matrix.json` + `docs/g0/RBAC.md`
- **Méthode** : croisement des 231 opérations d'API avec les 4 rôles, dérivé
  des dépendances de sécurité du code.
- **Acceptation** : chaque opération porte un rôle exigé explicite, ou est
  marquée `PUBLIC` avec justification écrite. Un test échoue si une route
  n'est ni l'un ni l'autre.
- **Faux si** : la matrice est déclarative et non dérivée du code.

> **Attention particulière.** Le cloisonnement comptable (`ACCOUNTANT` ne voit
> pas les patients) est déjà testé par le flux clinique. La matrice doit le
> confirmer, pas le contredire.

#### 6. Registre des données sensibles et flux externes

- **Livrable** : `docs/g0/DATA_AND_FLOWS.md` + `artifacts/g0/external-flows.json`
- **Méthode** : recensement des champs à caractère personnel ou de santé, de
  leur table, de leur usage ; et des **14 modules** faisant des appels sortants.
- **Acceptation** : chaque flux externe indique sa destination, son
  déclencheur, son état (actif / désactivé) et ce qu'il transporte. Les flux
  CSA (12 modules) et ONMCI (4) sont documentés comme **désactivés par défaut**.
- **Faux si** : un flux sortant existe sans figurer au registre.

> **Rappel de sécurité, non négociable.** Les journaux ne doivent porter aucun
> identifiant corrélable à un patient. Le registre doit le vérifier, pas
> l'affirmer.

#### 10. Secret scanning bloquant

- **Livrable** : modification de `.github/workflows/ci.yml`
- **Méthode** : le scan `detect-secrets` passe d'`advisory`
  (`continue-on-error: true`) à **bloquant**, et porte sur l'**historique
  complet**, pas seulement sur `HEAD`.
- **Acceptation** : un secret introduit dans une PR de test la fait échouer.
- **Faux si** : le scan reste en `continue-on-error`, ou ne couvre que le
  dernier commit.

> **Point à instruire avant de bloquer** : la baseline `.secrets.baseline`
> doit d'abord être auditée. Rendre bloquant un scan dont la baseline contient
> un vrai secret le figerait dans le dépôt.

#### 11. Proposition de protection de branche

- **Livrable** : mise à jour de
  `docs/governance/BRANCH_PROTECTION_PRE_TAG_REQUIRED_CHECKS.md`
- **Méthode** : le document existe déjà et liste les sept contrôles manquants.
  G0 y ajoute la commande exacte d'application et la vérification post-application.
- **Acceptation** : `BRANCH_PROTECTION_UPDATE_REQUIRED` reste affiché tant que
  la règle GitHub n'a pas été modifiée.
- **Faux si** : le document prétend que la règle est appliquée. **Cette
  proposition ne modifie pas la règle** — l'application relève d'une décision
  humaine distincte.

### Lot C — Qualité mesurable

Branche : `g0/quality-baseline`

#### 7. Couverture lignes et branches

- **Livrable** : `artifacts/g0/coverage.xml` + `docs/g0/COVERAGE.md`
- **Méthode** : `pytest-cov` avec `--cov-branch`, ajouté aux dépendances de
  développement et exécuté en CI.
- **Acceptation** : la couverture est **mesurée et publiée**. G0 ne fixe
  **aucun seuil** : une baseline constate, elle n'exige pas. Le seuil sera une
  décision de G1, prise en connaissance du chiffre.
- **Faux si** : un seuil est inventé sans mesure préalable, ou si la couverture
  est mesurée sur un sous-ensemble de tests choisi pour flatter le résultat.

> **Deux difficultés connues** : un test SSRF fige la suite complète sous
> Windows — la mesure devra donc se faire en CI Linux ; et certains tests
> partagent un état SQLite, ce qui rend l'ordre significatif. La mesure doit
> documenter la commande exacte utilisée.

#### 8. Baseline de performance reproductible

- **Livrable** : `scripts/g0_perf_baseline.py` + `artifacts/g0/perf-baseline.json`
- **Méthode** : scénario **synthétique** sur la stack Docker réelle —
  authentification, création patient, échantillon, résultat, facture — avec
  latences p50/p95/p99 et débit.
- **Acceptation** : le script est rejouable et produit des chiffres comparables
  d'une exécution à l'autre ; l'environnement de mesure est décrit (runner CI,
  ressources, volume de données).
- **Faux si** : les chiffres proviennent d'un poste de développement non
  décrit, ou si le scénario utilise des données patient réelles — **interdit**.

> Une baseline de performance qui ne dit pas sur quelle machine elle a été
> prise ne se compare à rien.

### Lot D — Consolidation

Branche : `g0/backlog-and-index`

#### 9. Backlog maître P0 / P1 / P2

- **Livrable** : `docs/g0/BACKLOG.md`
- **Méthode** : consolidation des constats **déjà écrits** — six alertes CodeQL
  hautes triées, `REQUIRE_VALIDATION_FOR_RELEASE=false` admis, compte technique
  CSA sur-privilégié côté `csa-plateau`, protection de branche incomplète,
  aucun automate physique qualifié, et les deux blocages juridiques ouverts.
- **Acceptation** : chaque entrée porte une **preuve** (fichier, ligne, run CI
  ou document), un impact et une action. Aucune entrée sans source.
- **Faux si** : le backlog contient des intentions sans constat, ou omet un
  constat déjà documenté.

#### 12. Index consolidé des preuves G0

- **Livrable** : `docs/g0/G0_EVIDENCE_INDEX.md`
- **Méthode** : table reliant chaque preuve à son artefact, au run CI qui l'a
  produit, et à son état de revue.
- **Acceptation** : les douze preuves y figurent avec un lien vérifiable.
  L'index affiche `G0_PASS` **uniquement** si les douze sont produites *et*
  revues.
- **Faux si** : l'index déclare `G0_PASS` sur des preuves produites mais non
  revues.

---

## Branches de travail

| Branche | Preuves | Créée depuis |
| --- | --- | --- |
| `g0/architecture-inventory` | 1, 2, 3, 4 | `main` @ `18bf868` |
| `g0/security-baseline` | 5, 6, 10, 11 | `main` @ `18bf868` |
| `g0/quality-baseline` | 7, 8 | `main` @ `18bf868` |
| `g0/backlog-and-index` | 9, 12 | `main` @ `18bf868` |

Quatre lots plutôt que douze branches : les preuves d'un même lot partagent
leur outillage et se relisent ensemble. Le lot D dépend des trois autres — son
index ne peut être complété qu'après eux.

**Ordre recommandé** : A, puis B et C en parallèle, puis D.

## Ce que G0 ne fait pas

- **Aucune fonctionnalité nouvelle.** Le gate mesure l'existant.
- **Aucun seuil de qualité fixé.** Une baseline constate ; les seuils relèvent
  de G1.
- **Aucun changement de gouvernance.** `REAL_DATA_NO_GO` et
  `DISTRIBUTION_NO_GO` sont conservés, CSA et interfaces automates restent
  désactivés.
- **Aucune modification de la protection de branche** — G0 la *propose*.
- **Aucun tag, aucune image, aucune release.**

## Critère de sortie

```
G0_PASS
```

**Ne se prononce qu'après production ET revue des douze preuves.** Produire
onze preuves sur douze ne vaut pas G0 : une baseline incomplète laisse
précisément le trou qu'on cherchera à combler plus tard, sans savoir qu'il
existe.

Statut actuel :

```
G0_PLAN_READY
G0_EVIDENCE_PENDING   (0 / 12 produites)
```
