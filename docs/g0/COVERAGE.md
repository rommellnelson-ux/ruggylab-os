# G0 — Couverture lignes et branches (preuve 7)

> **INTERNAL — SECURITY ARCHITECTURE**
> **BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT**
>
> Ce document décrit une architecture de référence, pas une installation. Il ne
> contient aucune adresse IP réelle de site, aucun identifiant, aucun secret,
> aucun nom de compte, aucune topologie VLAN réelle et aucune donnée patient —
> et il ne doit pas en recevoir tant que le dépôt reste public.
>
> Ce bandeau est une **mention de classification, pas un contrôle d'accès** : il
> n'empêche personne de lire ce fichier. Le seul contrôle réel serait la
> visibilité du dépôt.

> **Aucun seuil.** G0 constate. Le chiffre est publié tel qu'il sort de la
> mesure, favorable ou non. Fixer un seuil ici transformerait une baseline en
> verdict, et un verdict se contourne en choisissant les tests — c'est
> exactement ce que la campagne cherche à rendre impossible.
>
> Mesuré par la CI Linux (`.github/workflows/g0-quality.yml`, job
> **G0 — Coverage baseline**), résumé par
> [`scripts/g0_coverage_summary.py`](../../scripts/g0_coverage_summary.py).

## 1. Ce qui est mesuré, et ce qui ne l'est pas

C'est la section la plus importante du document. Un pourcentage de couverture
n'a de sens que rapporté à ce qui a effectivement traversé un interpréteur
Python instrumenté. Tout le reste — aussi utile soit-il par ailleurs — est
**absent de la mesure**, et le dire est la seule manière de ne pas laisser
croire l'inverse.

| Catégorie | Instrumenté ? | Contribue au chiffre ? |
| --- | --- | --- |
| Tests Python (unitaires, services, routes, schémas, sécurité applicative) | **Oui** — `pytest --cov` | Oui |
| Tests adossés à PostgreSQL 16 (9 fichiers `*_postgres.py`) | **Oui** — `pytest --cov`, base réellement migrée | Oui |
| Flux clinique de bout en bout (`scripts/uat_smoke.py`) | **Oui** — l'application est lancée sous `coverage run --parallel-mode` | Oui |
| Flux clinique à travers le proxy TLS (job `docker-stack` de `ci.yml`) | **Non** — l'application tourne dans un conteneur non instrumenté | Non |
| Sauvegarde / restauration PostgreSQL (job `backup-restore`) | **Non** — processus applicatif non instrumenté | Non |
| Parcours d'interface (`scripts/*_playwright.js`, 4 fichiers) | **Non** — pilotage par navigateur, aucune donnée de couverture Python | Non |
| Migrations Alembic (`alembic/`) | Hors périmètre déclaré | Non — `source = ["app"]` |
| Scripts d'exploitation (`scripts/`) | Hors périmètre déclaré | Non |

> **Ce que cela implique.** Un endpoint exercé uniquement par un test Playwright
> ou par le smoke test à travers le proxy apparaît **non couvert** dans ce
> document. C'est voulu : il n'a pas été mesuré. L'inverse — le compter comme
> couvert parce qu'« il existe un test quelque part » — produirait un chiffre
> auquel on ne pourrait plus se fier du tout.

## 2. Commande exacte

Trois processus instrumentés, puis une combinaison. Chacun écrit son propre
fichier de données ; `coverage combine` les fusionne avant que le moindre
rapport soit produit. Publier l'un des trois isolément reviendrait à publier la
plus flatteuse des trois mesures.

```bash
# 1. Suite complète
python -m pytest \
  --cov=app --cov-branch \
  --cov-report=xml:"$RUNNER_TEMP/coverage-suite.xml" \
  --cov-report=json:"$RUNNER_TEMP/coverage-suite.json" \
  --cov-report=term-missing
mv .coverage .coverage.suite

# 2. Tests adossés à PostgreSQL (base migrée par `alembic upgrade head`)
python -m pytest --cov=app --cov-branch --cov-report=term \
  tests/test_clinical_safety_postgres.py \
  tests/test_analyzer_idempotency_r6_postgres.py \
  tests/test_lab_numbering_r5_postgres.py \
  tests/test_preanalytic_cancelled_sample_postgres.py \
  tests/test_quality_transaction_postgres.py \
  tests/test_finance_transaction_postgres.py \
  tests/test_imaging_transaction_postgres.py \
  tests/test_auth_session_postgres.py \
  tests/test_equipment_registry_postgres.py
mv .coverage .coverage.postgres

# 3. Flux clinique E2E, application elle-même instrumentée
python -m coverage run --parallel-mode --branch --source=app \
  -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
python -m scripts.uat_smoke
kill -INT <pid>          # l'arrêt gracieux écrit les données de couverture

# 4. Combinaison et rapports définitifs
python -m coverage combine
python -m coverage xml  -o artifacts/g0/coverage.xml
python -m coverage json -o artifacts/g0/coverage.json
python -m coverage report --show-missing

# 5. Résumé structuré, puis contrôle de validité
python scripts/g0_coverage_summary.py --generate --print-summary
python scripts/g0_coverage_summary.py --check
```

> **Pourquoi l'arrêt par SIGINT compte.** `coverage` n'écrit ses données qu'à la
> fin du processus mesuré. Un `kill -9` sur uvicorn perdrait silencieusement
> toute la couverture du flux clinique : le pourcentage baisserait sans que rien
> ne l'explique. Le job vérifie donc que le processus s'est bien arrêté, et
> échoue sinon.

### Réglages de mesure

Déclarés dans [`pyproject.toml`](../../pyproject.toml), sections
`[tool.coverage.run]` et `[tool.coverage.report]` :

| Réglage | Valeur | Pourquoi |
| --- | --- | --- |
| `branch` | `true` | Sans branches, `if a and b` compte pour couvert dès qu'une seule combinaison passe |
| `source` | `["app"]` | Le périmètre est l'application, pas les scripts ni les migrations |
| `relative_files` | `true` | Trois processus produisent des données ; des chemins absolus ne se recouperaient pas |
| `include_namespace_packages` | `true` | **Correction de mesure, voir ci-dessous** |
| `fail_under` | *absent* | Aucun seuil, jamais |

> **Un défaut de mesure trouvé par le contrôle de périmètre.**
> `app/api/middleware/` et `app/ml/` n'ont pas de `__init__.py`. Sans
> `include_namespace_packages`, `coverage` cesse de descendre dans un répertoire
> qui n'est pas un paquet : `app/api/middleware/rate_limit.py` et
> `app/ml/model_server.py` **disparaissaient purement et simplement du rapport**
> — ni couverts, ni signalés non couverts, juste absents. Le pourcentage global
> s'en trouvait mécaniquement embelli. Le contrôle de `--check`, qui compare la
> liste des fichiers rapportés à l'arborescence réelle de `app/`, l'a détecté :
> 228 modules rapportés pour 230 présents.

### Trois pourcentages, et lequel lire

`coverage report` affiche un `TOTAL` unique — **45 %** pour cette mesure — qui
n'est ni la couverture de lignes ni celle des branches : c'est le rapport
`(instructions couvertes + arcs de branche couverts) / (instructions + arcs)`.
Ce document publie les deux grandeurs **séparément**, parce qu'un chiffre mêlé
masque exactement l'écart qui compte ici : les lignes sont couvertes à environ
la moitié, les branches à environ un huitième. Confondre les deux laisserait
croire que le code est bien mieux exercé qu'il ne l'est sur ses chemins
conditionnels.

## 3. Exclusions

Aucune exclusion n'a été ajoutée pour cette campagne. Le seul motif actif est
celui que `coverage` applique par défaut, `# pragma: no cover`, présent
**10 fois** dans `app/` :

| Fichier | Ligne | Nature |
| --- | --- | --- |
| `app/core/login_rate_limit.py` | 105 | Branche d'erreur Redis indisponible à l'exécution |
| `app/core/rate_limit.py` | 93 | Branche d'erreur Redis indisponible à l'exécution |
| `app/services/analyzers/factory.py` | 38 | Garde-fou défensif (parseur inconnu) |
| `app/services/interfacing/dymind_dh36.py` | 15 | Frontière défensive du parseur automate |
| `app/services/malaria_ai.py` | 281 | Frontière défensive de l'inférence |
| `app/services/redis_notification.py` | 64, 66 | Arrêt propre et erreur générique |
| `app/services/token_cleanup.py` | 92 | Erreurs transitoires de base de données |
| `app/utils/redis_rate_limiter.py` | 23, 46 | `TYPE_CHECKING` et erreur Redis |

> **Ce que ces exclusions coûtent.** Huit d'entre elles masquent des **branches
> d'erreur** — précisément les chemins qu'un laboratoire emprunte quand Redis
> tombe ou qu'un automate envoie une trame inattendue. Elles ne sont pas
> illégitimes, mais elles ne sont pas neutres : le mode dégradé est donc
> **moins mesuré que le mode nominal**, et la question de savoir s'il est testé
> ailleurs revient au lot D. Aucune n'a été ajoutée par cette campagne.
>
> Aucun motif supplémentaire n'a été déclaré (`if TYPE_CHECKING:`,
> `raise NotImplementedError`, `__repr__`…) : chacun aurait fait monter le
> pourcentage sans qu'une seule ligne de plus soit exécutée.

## 4. Résultats mesurés

<!-- RESULTATS_COUVERTURE_DEBUT -->

> Exécution de CI : [34363173460 / job 102505088553](https://github.com/rommellnelson-ux/ruggylab-os/actions/runs/34363173460/job/102505088553), commit `fa45c84`
> · coverage 7.16.0 · branches mesurées : `true` · empreinte des entrées `f668163e78453e8d…` sur 373 fichiers.

### 4.1 Totaux

| Mesure | Valeur |
| --- | --- |
| Instructions totales | **12712** |
| Instructions couvertes | **6606** |
| Instructions non couvertes | **6106** |
| **Couverture lignes** | **51.97 %** |
| Branches totales | **2530** |
| Branches couvertes | **326** |
| Branches partielles | 242 |
| Branches non couvertes | **2204** |
| **Couverture branches** | **12.89 %** |
| Modules mesurés | 230 |
| Modules jamais exécutés | **24** |
| Lignes exclues (`# pragma: no cover`) | 34 |

Croisement XML/JSON : `lines-valid=12712`, `lines-covered=6606`, `branches-valid=2530`, `branches-covered=326`, 1265 attributs `condition-coverage` — les deux sources concordent.

### 4.2 Par regroupement

> Les regroupements s'imbriquent : `app/services` contient `app/services/validation`, `interfacing` et `csa_sync`. Les deux sont publiés — vouloir des ensembles disjoints donnerait des chiffres que personne ne saurait recomposer.

| Regroupement | Modules | Instructions | Couvertes | Lignes % | Branches % |
| --- | ---: | ---: | ---: | ---: | ---: |
| `app/api` | 58 | 3334 | 1503 | **45.08 %** | **12.5 %** |
| `app/core` | 18 | 926 | 456 | **49.24 %** | **15.24 %** |
| `app/models` | 6 | 736 | 736 | **100.0 %** | **0.0 %** |
| `app/services` | 79 | 4851 | 1520 | **31.33 %** | **12.45 %** |
| `app/services/csa_sync` | 6 | 279 | 0 | **0.0 %** | **0.0 %** |
| `app/services/interfacing` | 5 | 369 | 144 | **39.02 %** | **25.58 %** |
| `app/services/validation` | 4 | 145 | 85 | **58.62 %** | **34.62 %** |
| `app/utils` | 8 | 241 | 72 | **29.88 %** | **1.85 %** |

### 4.3 Les dix plus gros volumes non couverts

| Module | Instructions non couvertes | Instructions | Lignes % | Branches % |
| --- | ---: | ---: | ---: | ---: |
| `app/api/v1/endpoints/reports.py` | **323** | 410 | 21.22 % | 0.0 % |
| `app/services/equipment_registry.py` | **206** | 385 | 46.49 % | 26.87 % |
| `app/services/pdf_prescription.py` | **187** | 221 | 15.38 % | 0.0 % |
| `app/api/v1/endpoints/results.py` | **171** | 271 | 36.9 % | 7.14 % |
| `app/services/interfacing/raw_tcp_listener.py` | **152** | 152 | 0.0 % | 0.0 % |
| `app/core/secrets_manager.py` | **151** | 151 | 0.0 % | 0.0 % |
| `app/services/code_mapping_service.py` | **138** | 174 | 20.69 % | 4.55 % |
| `app/api/v1/endpoints/equipments.py` | **130** | 197 | 34.01 % | 0.0 % |
| `app/services/report_signing.py` | **122** | 148 | 17.57 % | 0.0 % |
| `app/services/report_delivery_outbox.py` | **121** | 121 | 0.0 % | 0.0 % |

### 4.4 Modules cliniques critiques

> Un pourcentage global noie ces modules : 90 % de couverture globale est compatible avec 0 % sur la vérification des valeurs critiques. Ils sont donc suivis nommément.

| Module | Instructions | Couvertes | Lignes % | Branches % |
| --- | ---: | ---: | ---: | ---: |
| `app/services/auto_validator.py` | 42 | 16 | **38.1 %** | 6.25 % |
| `app/services/critical_checker.py` | 28 | 8 | **28.57 %** | 5.56 % |
| `app/services/critical_notifier.py` | 47 | 12 | **25.53 %** | 0.0 % |
| `app/services/delta_checker.py` | 58 | 13 | **22.41 %** | 5.56 % |
| `app/services/exam_order_service.py` | 87 | 79 | **90.8 %** | 69.23 % |
| `app/services/malaria_ai.py` | 109 | 51 | **46.79 %** | 12.5 % |
| `app/services/preanalytic.py` | 17 | 11 | **64.71 %** | 33.33 % |
| `app/services/reference_checker.py` | 51 | 12 | **23.53 %** | 3.33 % |
| `app/services/result_service.py` | — | — | *absent du rapport* | — |
| `app/services/validation/med_logic.py` | 90 | 67 | **74.44 %** | 45.0 % |
| `app/services/validation/poct_reference.py` | 34 | 18 | **52.94 %** | 0.0 % |
| `app/services/validation/precis_expert.py` | 21 | 0 | **0.0 %** | 0.0 % |

### 4.5 Modules jamais exécutés

**24** modules n'ont vu aucune de leurs instructions exécutée par les trois processus instrumentés. Ce n'est pas nécessairement du code mort : certains ne se chargent qu'en présence d'un automate, d'une configuration ou d'un rôle de processus absent de la CI. Les classer relève du lot D.

- `app/analyzer_gateway.py`
- `app/api/middleware/rate_limit.py`
- `app/core/cache_decorator.py`
- `app/core/ratios.py`
- `app/core/secrets_manager.py`
- `app/ml/model_server.py`
- `app/scheduler.py`
- `app/services/analyzers/__init__.py`
- `app/services/analyzers/anbio_immuno.py`
- `app/services/analyzers/base.py`
- `app/services/analyzers/dymind_biochemistry.py`
- `app/services/analyzers/dymind_hematology.py`
- `app/services/analyzers/factory.py`
- `app/services/analyzers/registry.py`
- `app/services/csa_sync/__init__.py`
- `app/services/csa_sync/client.py`
- `app/services/csa_sync/exam_map.py`
- `app/services/csa_sync/health.py`
- `app/services/csa_sync/inbound.py`
- `app/services/csa_sync/outbound.py`
- `app/services/interfacing/raw_tcp_listener.py`
- `app/services/report_delivery_outbox.py`
- `app/services/validation/precis_expert.py`
- `app/utils/url_safety.py`

<!-- RESULTATS_COUVERTURE_FIN -->

> **Sur quelle révision ces chiffres portent-ils ?** Ils viennent de
> l'exécution citée ci-dessus, prise sur le commit `fa45c84`. Les commits
> suivants de cette branche ne touchent que `docs/g0/*.md` — aucun fichier des
> ensembles d'entrée `coverage` (`app/**`, `tests/**`, `pyproject.toml`,
> `requirements.txt`, le générateur du résumé) ni `performance` (le script de
> mesure, la surcharge, `app/**`, `alembic/**`, `docker-compose.yml`,
> `Dockerfile`, `requirements.txt`). La mesure décrit donc bien le code de la
> tête de branche. Chaque nouvelle exécution du workflow en produit une autre,
> nécessairement différente sur les latences : c'est la raison pour laquelle ces
> artefacts ne sont pas versionnés, et pourquoi la version publiée ici porte
> l'identifiant de l'exécution qui l'a produite.

## 5. Limites de cette campagne

1. **La couverture ne mesure pas la qualité des assertions.** Une ligne exécutée
   par un test qui n'affirme rien est comptée couverte. Le chiffre borne ce qui
   *pourrait* être détecté, il ne dit pas ce qui *est* vérifié.
2. **Trois processus instrumentés, pas quatre.** Le flux clinique passant par le
   proxy TLS (`docker-stack`) et les parcours Playwright ne contribuent pas.
   Instrumenter le conteneur applicatif supposerait de modifier l'image mesurée,
   donc de ne plus mesurer l'image livrée.
3. **L'ordre des tests est significatif.** Une partie de la suite partage un état
   SQLite ; deux exécutions dans un ordre différent peuvent ne pas couvrir
   exactement les mêmes lignes. La commande publiée est celle qui a produit les
   chiffres.
4. **Un module jamais importé n'est pas nécessairement du code mort.** Il peut
   n'être chargé qu'en présence d'un automate, d'une configuration ou d'un rôle
   de processus absent de la CI. Le classer relève du lot D.
5. **La mesure porte sur une révision.** Elle ne dit rien de la révision
   suivante, et n'est pas versionnée pour cette raison : re-mesurer ne redonne
   pas les mêmes chiffres, aucun contrôle ne pourrait donc détecter qu'un
   fichier versionné est périmé.

## 6. Non-vacuité des contrôles

Un contrôle qu'aucune mutation ne fait échouer est décoratif. Chacun de ceux qui
protègent cette mesure a été rejoué contre une altération connue, dans
[`tests/test_g0_quality_baseline.py`](../../tests/test_g0_quality_baseline.py),
avec à chaque fois un **témoin** exigeant l'inverse sur la mesure intacte :

| Mutation appliquée | Refus attendu |
| --- | --- |
| `--cov-branch` retiré | `branches non mesurees` |
| XML sans attribut `condition-coverage` | `XML sans attribut condition-coverage` |
| Totaux XML absents | `XML incomplet` |
| Regroupement `app/services/csa_sync` supprimé | `regroupement absent` |
| Un module de `app/` retiré du rapport | `perimetre reduit` |
| Rapport de branches sans données de branches | `condition-coverage` |
| XML et JSON en désaccord | `incoherence XML/JSON` |
| XML tronqué | `ParseError` |

Les charges utiles de ces tests sont **construites dans le test**, jamais lues
dans un artefact versionné : un test qui relirait un fichier produit avant la
mutation passerait alors même que le générateur serait cassé.

## 7. Provenance

Le résumé porte sa provenance (ensemble d'entrée `coverage` de
[`scripts/g0_provenance.py`](../../scripts/g0_provenance.py)) : empreinte
SHA-256 des octets réellement lus — `app/**`, `tests/**`, `pyproject.toml`,
`requirements.txt`, `scripts/g0_coverage_summary.py`. `.github/**` en est
volontairement absent : la CI **orchestre** la mesure, elle ne la détermine pas,
et l'y inclure rendrait l'empreinte instable à chaque retouche d'un job sans
rapport.

Les fichiers `coverage.xml`, `coverage.json` et `coverage-summary.json` sont
produits à chaque exécution du workflow et publiés comme artefacts de CI
(`g0-coverage-baseline`, conservés 90 jours). Ils ne sont **pas versionnés** :
une mesure versionnée serait une preuve que rien ne peut contredire.
