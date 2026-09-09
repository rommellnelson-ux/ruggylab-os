# G0 — Matrice RBAC et qualification des routes particulières

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

> **L'autorisation n'est jamais déduite du nom d'une route.** Elle vient des
> dépendances FastAPI réellement appliquées, de la lecture du corps de la
> fonction, ou d'une sonde exécutée contre l'application. Une matrice écrite à
> partir des intitulés aurait décrit une application imaginaire.
>
> Généré par
> [`scripts/g0_security_baseline.py`](../../scripts/g0_security_baseline.py),
> à partir de [`artifacts/g0/routes.json`](../../artifacts/g0/routes.json)
> produit par le lot A. Aucune liste de routes n'est réécrite à la main.
> Matrice : [`artifacts/g0/rbac-matrix.json`](../../artifacts/g0/rbac-matrix.json).
> Provenance : [`artifacts/g0/security-provenance.json`](../../artifacts/g0/security-provenance.json).

## 1. Ce qui est mesuré, et ce qui ne l'est pas

Le lot B **photographie et qualifie**. Il ne corrige rien. Chaque écart relevé
ici est transmis au **lot D**, qui décidera s'il faut le traiter et comment.
Corriger un défaut dans la même passe que sa mesure rendrait la mesure
invérifiable : on ne saurait plus si le système était ainsi ou s'il a été rendu
ainsi pour la photographie.

| | |
| --- | --- |
| Opérations couvertes | **231** — les 231 opérations OpenAPI du lot A, sans exception |
| Rôles | `accountant`, `admin`, `officer`, `technician` |
| Sondes exécutées | **99**, contre l'application, sur une base SQLite jetable |
| Données des sondes | **strictement synthétiques** — aucune donnée patient réelle |
| Non résolues | **0** |

## 2. Niveaux de confiance

Une matrice qui affirme tout avec la même assurance ne dit pas ce qu'elle sait.
Chaque opération porte donc le niveau de preuve de ce qui est écrit à son sujet.

| Niveau | Opérations | Ce que cela signifie |
| --- | ---: | --- |
| `STATIC_EXPLICIT` | **168** | La garde est lue dans les dépendances FastAPI réellement appliquées à la route. Aucune sonde ne l'a exercée. |
| `RUNTIME_CONFIRMED` | **62** | Une sonde a atteint l'autorisation et le code HTTP observé confirme la lecture statique. |
| `CUSTOM_AUTH_CONFIRMED` | **1** | La garde n'est pas une dépendance : elle est écrite dans le corps de la fonction (`_verify_analyzer_security`), et une sonde l'a exercée. |
| `UNRESOLVED` | **0** | Aucune opération ne reste sans qualification. |

`STATIC_EXPLICIT` n'est pas une faiblesse de méthode : c'est l'aveu que 168
opérations sont décrites par lecture et non par expérience. Sonder les 231
demanderait de construire un corps de requête valide pour chacune, donc
d'inventer des données cliniques — ce que la baseline s'interdit.

## 3. Sémantique réelle des gardes

Trois d'entre elles n'autorisent rien : elles **authentifient**. Les confondre
avec une autorisation reviendrait à compter 231 opérations protégées par rôle.

| Garde | Nature | Rôles admis | Ce qu'elle fait réellement |
| --- | --- | --- | --- |
| `get_current_user` | authentification | les 4 | Décode le JWT, refuse un jeton révoqué (denylist par `jti`) et un jeton dont `ver` ne correspond plus à `user.auth_version`. **Aucun contrôle de rôle.** |
| `get_current_active_user` | authentification | les 4 | Refuse un compte désactivé (403). **Aucun contrôle de rôle.** |
| `require_admin` | autorisation | `admin` | `role == ADMIN`, sinon 403. |
| `require_officer` | autorisation | `admin`, `officer` | `role ∈ {OFFICER, ADMIN}`, sinon 403. |
| `require_finance` | autorisation | `accountant`, `admin` | `role ∈ {ACCOUNTANT, ADMIN}`, sinon 403. Séparation des tâches. |
| `forbid_accountant` | autorisation | `admin`, `officer`, `technician` | `role != ACCOUNTANT`, sinon 403. Cloisonnement clinique / gestion. |
| `_verify_analyzer_security` | jeton machine | aucun | Exige `ANALYZER_API_KEY` (comparaison à temps constant), filtre d'IP optionnel, signature HMAC-SHA256 horodatée optionnelle. Aucun compte, aucun rôle : ce n'est pas une identité humaine. |

## 4. D'où vient l'autorisation, opération par opération

| Source | Opérations |
| --- | ---: |
| `fastapi_role_dependency` | **150** |
| `authentication_only` | **51** |
| `none` (aucune dépendance de sécurité) | **15** |
| `fastapi_role_dependency` + cloisonnement en couche service | **14** |
| `custom_endpoint_guard` | **1** |

Les 14 opérations à cloisonnement de service portent une garde de rôle **et**
un filtrage par périmètre appliqué dans le service (`can_access_patient`,
`can_access_result`) : le rôle donne l'entrée, le périmètre décide de ce qui est
visible une fois entré.

### Portée réelle par rôle

Nombre d'opérations qu'un compte de ce rôle peut atteindre, sur 231 :

| Rôle | Opérations atteintes |
| --- | ---: |
| `admin` | **215** |
| `officer` | **163** |
| `technician` | **116** |
| `accountant` | **70** |

### Les 51 opérations à authentification seule

Elles n'exercent **aucun contrôle de rôle** : tout compte actif les atteint, y
compris le comptable, que `forbid_accountant` écarte pourtant partout ailleurs.
Huit d'entre elles touchent à la santé ou à l'opérationnel militaire :

```
GET  /api/v1/military-facilities
POST /api/v1/aes
POST /api/v1/bioref/interpret
POST /api/v1/fhir/medication-dispense
POST /api/v1/fhir/supply-delivery
POST /api/v1/prescription/interactions
POST /api/v1/prescription/report
POST /api/v1/prescription/scan
```

Constat **B-01**, classé **P1**. Voir
[`SECURITY_FINDINGS.md`](SECURITY_FINDINGS.md).

## 5. Sondes dynamiques — ce que l'application fait réellement

99 sondes, exécutées avec de vrais jetons émis pour cinq comptes synthétiques
et un appelant anonyme. `expected` exprime la **règle métier attendue**, pas ce
que le code fait : un écart décrit donc l'application telle qu'elle est, et non
une sonde défaillante.

| Compte | Rôle | Sondes | Attendu ALLOW | Attendu DENY | Écarts |
| --- | --- | ---: | ---: | ---: | ---: |
| `admin` | `admin` | 8 | 8 | 0 | 0 |
| `officer` | `officer` | 20 | 5 | 15 | 0 |
| `technician` | `technician` | 29 | 8 | 21 | **1** |
| `technician_unit_a` | `technician`, unité `G0-UNITE-A` | 4 | 1 | 3 | 0 |
| `accountant` | `accountant` | 32 | 13 | 19 | **2** |
| `<anonyme>` | — | 6 | 0 | 6 | 0 |
| **Total** | | **99** | **35** | **64** | **3** |

Codes HTTP observés : 403 (55), 200 (32), 401 (6), 201 (3), 404 (2), 422 (1).
98 sondes ont **atteint l'autorisation** ; une seule s'est arrêtée avant, sur
une validation de corps de requête (`POST /api/v1/samples`, 422), et elle est
classée `VALIDATION_FAILED_BEFORE_AUTHORIZATION` — la compter comme une preuve
d'autorisation aurait été une preuve fausse.

### Les trois écarts

| Sonde | Observé | Attendu | Lecture |
| --- | --- | --- | --- |
| `accountant` → `POST /api/v1/aes` | **201** | DENY | Le comptable **crée** une déclaration d'accident d'exposition au sang, dossier qui porte le statut sérologique VIH/VHB/VHC du patient source. |
| `accountant` → `POST /api/v1/quality/non-conformities` | **201** | DENY | Le comptable ouvre une non-conformité qualité. |
| `technician` → `POST /api/v1/billing/calculate` | **200** | DENY | Un technicien déclenche un calcul de facturation. |

Constat **B-08**, classé **P1**. Ces trois routes n'ont pas de garde de rôle :
elles relèvent des 51 opérations à authentification seule. L'écart n'est donc
pas un bogue de la sonde mais la conséquence directe du §4.

### Cloisonnement par unité

La sonde `technician_unit_a` accède à un patient de son unité et se voit refuser
celui de l'unité B : le cloisonnement **fonctionne par l'API**. Il ne repose que
sur du code applicatif — le lot A n'a relevé **aucune politique RLS** dans la
base. Constat **B-07**, P2.

## 6. Routes particulières — capacité réelle, pas intitulé

Huit surfaces ont été exercées une par une, parce que leur qualification par la
seule lecture aurait été soit alarmiste, soit rassurante à tort. Le tableau
donne la **capacité réellement obtenue**, l'expiration, la rejouabilité et les
traces laissées.

### 6.1 `GET /app/map` — P1

Constat du lot A **confirmé** : HTTP **200 sans jeton**. Le gabarit expose le
titre « Cartographie des EHM et Gendarmerie », l'intitulé « Établissements
Hospitaliers Militaires », la mention « DIVISION SANTÉ — 2026 », les catégories
HMA, CMA, CSA, Armées et Gendarmerie, et les effectifs agrégés statiques
**60 / 1 / 8 / 51 / 37 / 22** — **sans coordonnées ni liste détaillée**, qui
restent derrière `GET /api/v1/military-facilities`.

Un ordre de grandeur du dispositif de santé militaire est donc lisible sans
authentification. Ce n'est pas « la seule existence de la fonctionnalité » :
minimiser ici clôturerait l'examen à tort. Ce n'est pas non plus un P0 — cela
exigerait une règle de classification institutionnelle qui n'existe pas dans le
dépôt. Rejouable sans limite. Requête tracée par `ObservabilityMiddleware`
(chemin, IP cliente, agent). Remédiation : **lot D**.

### 6.2 `GET /api/v1/reports/verify/{token}` — P1

Le jeton `rs-<id>-<HMAC-SHA256>` est **le seul facteur d'accès**. Il **n'expire
jamais**, n'est pas révocable indépendamment du compte rendu, et il est
**rejouable sans limite**. La base n'en stocke que l'empreinte SHA-256.

La réponse ne contient **aucune identité patient ni valeur biologique** :
`status`, `snapshot_id`, `result_id`, `version_number`, `document_status`,
`created_at`, `pdf_sha256`, `revoked_at`. L'impact d'une fuite se borne donc à
la confirmation d'existence et à l'état d'un compte rendu — ce qui n'est pas
rien, et n'est pas une identité.

Le jeton étant porté par le **chemin** de l'URL, `ObservabilityMiddleware` le
journalise en clair à l'entrée et à la sortie. **Mesuré** par la sonde
sentinelle. Constat **B-03**.

### 6.3 `POST /api/v1/login/refresh` — P2

Non authentifiée au sens des dépendances FastAPI, mais **non anonyme** : le
jeton de rafraîchissement opaque fait office d'authentification, son empreinte
SHA-256 est comparée en base, la validité et l'activité du compte sont
contrôlées, et la **rotation à usage unique** borne le rejeu. La réserve du lot
A est levée. Un jeton inexistant reçoit **401**. Échéance : 30 jours. Aucune
limitation de débit propre à cette route.

### 6.4 `POST /api/v1/login/logout` — P2

La crainte du lot A — révoquer le jeton d'un tiers — **n'est pas confirmée** :
révoquer suppose de connaître la valeur du jeton, qui *est* le facteur
d'autorisation. La route répond **204** à un appel anonyme au corps vide comme
à un jeton inexistant : elle ne renseigne pas l'appelant, ce qui est le bon
comportement. Elle n'est pas limitée en débit par une garde propre. La valeur
du jeton circule dans le **corps**, donc hors du journal, qui n'écrit que le
chemin.

### 6.5 `POST /api/v1/analyzer/results` — P2

Ce n'est **pas** une route ouverte. Sans `ANALYZER_API_KEY` configurée, elle
répond **503** : *fail-closed*. La réserve du lot A est levée. La signature
HMAC-SHA256 horodatée et le filtrage d'IP restent **optionnels** : sans eux, la
seule protection est une clé statique qui n'expire pas. L'idempotence
applicative limite l'effet d'un doublon.

### 6.6 `WEBSOCKET /api/v1/notifications/ws` — P2

Garde réelle, et **rechargée en cours de connexion** (~15 s), ce qui vaut mieux
qu'un contrôle à la seule ouverture. Denylist par `jti` vérifiée, compte actif
vérifié, rôle `ACCOUNTANT` refusé, cinq connexions simultanées au maximum.

Écart mesuré : `_authenticate_ws_token` **ne vérifie pas `auth_version`**, alors
que `get_current_user` le fait. Un jeton émis avant une modification sensible du
compte reste donc accepté sur le WebSocket jusqu'à son échéance (60 minutes),
alors qu'il est refusé sur l'API HTTP. Constat **B-04**. Le repli `?token=`
expose la valeur du jeton à tout journal d'URL en amont ; le middleware
applicatif ne journalise que le chemin, donc il ne l'écrit pas — un proxy qui
journaliserait l'URL complète l'écrirait.

### 6.7 `OPTIONS /{path_name:path}` (attrape-tout) — P2

Sans garde, mais **sans capacité** : 200 vide sur tout chemin, existant ou non,
aucun traitement, aucune énumération possible puisque la réponse est identique
partout. Elle masque en revanche les en-têtes CORS calculés par le middleware,
que la préflight n'atteint jamais sur les chemins qu'elle attrape.

### 6.8 `/metrics`, `/docs`, `/redoc`, `/openapi.json` — P2

Depuis le réseau Docker interne, en s'adressant directement à `app:8000`, ces
chemins répondent **200 sans aucune authentification** : métriques
d'exploitation et **contrat OpenAPI intégral des 231 opérations**. La protection
est entièrement portée par le proxy (`respond @internal 404` dans
`deploy/Caddyfile`), pas par l'application. Elle tient tant que le seul chemin
d'accès passe par lui : un conteneur compromis sur le réseau `backend`, ou un
port publié par erreur, la contourne. Le job CI `docker-stack` vérifie le 404 au
proxy ; **rien ne vérifie l'absence de chemin direct**.

## 7. Ce que cette matrice ne prouve pas

- Elle décrit **qui peut appeler quoi**, pas ce que la réponse contient. Une
  route autorisée peut renvoyer plus que nécessaire ; le filtrage de charge
  utile n'a pas été inventorié champ par champ.
- Les 168 opérations `STATIC_EXPLICIT` sont décrites par lecture des
  dépendances. Une garde écrite dans le corps d'une fonction et non déclarée
  comme dépendance n'apparaîtrait pas — une seule a été trouvée
  (`_verify_analyzer_security`), et rien ne garantit qu'il n'y en a pas
  d'autres dans des fonctions non sondées.
- Les sondes tournent sur **SQLite**, pas sur PostgreSQL. L'autorisation ne
  dépend pas du moteur, mais un comportement lié à une contrainte spécifique à
  PostgreSQL échapperait à cette mesure.
- Aucune conclusion de gouvernance n'est tirée ici. `CLINICAL_STATUS` reste
  `REAL_DATA_NO_GO`, `DISTRIBUTION_STATUS` reste `DISTRIBUTION_NO_GO`.

## 8. Rejouer la mesure

```
python scripts/g0_security_baseline.py --generate --print-summary
python scripts/g0_security_baseline.py --check
python -m pytest -q tests/test_g0_security_baseline.py
```

Le job CI **`G0 — Security baseline and secret scan`** régénère les artefacts,
les compare aux fichiers versionnés et échoue sur divergence. Il ne les met
jamais à jour de lui-même.
