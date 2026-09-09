# G0 — Constats de sécurité du lot B

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

> **Rien n'est corrigé ici.** Chaque constat est mesuré, classé et transmis au
> **lot D**, qui décidera s'il faut le traiter et comment. Corriger dans la même
> passe que la mesure rendrait la mesure invérifiable : on ne saurait plus si le
> système était ainsi, ou s'il a été rendu ainsi pour la photographie.
>
> Constats B-01 à B-09 : générés dans
> [`artifacts/g0/rbac-matrix.json`](../../artifacts/g0/rbac-matrix.json), champ
> `findings`. Constats B-10 et B-11 : mesurés par
> [`scripts/g0_secret_gate.py`](../../scripts/g0_secret_gate.py).

## 1. Échelle de classement

| Rang | Ce qu'il signifie ici |
| --- | --- |
| **P0** | Compromission directe de données de santé ou d'identité, sans authentification, atteignable depuis l'extérieur du périmètre. |
| **P1** | Exposition réelle d'information sensible, ou franchissement d'une séparation des tâches, dans une situation atteignable. |
| **P2** | Faiblesse structurelle, angle mort de traçabilité, ou dépendance à une protection portée par un autre composant. |

**Aucun constat P0 n'a été relevé.** Ce n'est pas une clause de style : aucun
chemin mesuré ne permet d'obtenir une identité patient ou un résultat biologique
sans authentification. Les routes publiques recensées renvoient soit un gabarit
statique, soit une réponse non nominative.

Prononcer un verdict de franchissement du gate sur cette base serait usurper
une décision qui n'appartient pas au lot B. `CLINICAL_STATUS` reste `REAL_DATA_NO_GO` ; `DISTRIBUTION_STATUS`
reste `DISTRIBUTION_NO_GO`.

## 2. Synthèse

| ID | Classement | Titre | Preuve |
| --- | :-: | --- | --- |
| B-01 | **P1** | Des opérations touchant à la santé n'ont aucune garde de rôle | matrice + sonde |
| B-03 | **P1** | Le jeton de vérification d'un compte rendu est journalisé en clair | sonde sentinelle |
| B-08 | **P1** | L'application s'écarte de la séparation des tâches attendue | 3 sondes sur 99 |
| B-09 | **P1** | Des données patient synthétiques apparaissent hors de l'audit métier | sonde sentinelle |
| B-10 | **P1** | La recherche de secrets de la CI était décorative | exécution du scan |
| B-02 | **P2** | Le modèle `military_facilities` n'a aucune table dans la base migrée | schéma introspecté |
| B-04 | **P2** | Le WebSocket ne vérifie pas `auth_version` | lecture du code |
| B-05 | **P2** | Aucun journal d'accès au proxy | lecture du `Caddyfile` |
| B-06 | **P2** | Aucune durée de conservation définie pour les données cliniques | classification |
| B-07 | **P2** | Le cloisonnement par unité ne repose que sur le code applicatif | sonde + schéma |
| B-11 | **P2** | `.secrets.baseline` est inutilisable sur un runner Linux | lecture du fichier |

**5 constats P1, 6 constats P2, 0 constat P0.**

## 3. Constats P1

### B-01 — Des opérations touchant à la santé n'ont aucune garde de rôle

**Constat.** 51 des 231 opérations n'exercent qu'une authentification : tout
compte actif les atteint, y compris le comptable, que `forbid_accountant` écarte
pourtant partout ailleurs. Parmi elles, **8 touchent à la santé ou à
l'opérationnel militaire** :

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

**Preuve.** Dérivé de `artifacts/g0/routes.json` — donc des dépendances FastAPI
réellement appliquées — et **confirmé par sonde** : `POST /api/v1/aes` est
accepté (HTTP 201) pour le compte comptable, alors que ce dossier porte le
statut sérologique VIH/VHB/VHC du patient source.

**Portée.** Ce n'est pas une absence d'authentification : un jeton reste exigé.
C'est une absence de **séparation des rôles** sur des surfaces qui en
appelleraient une.

**Remédiation : lot D.**

### B-03 — Le jeton de vérification d'un compte rendu est journalisé en clair

**Constat.** `GET /api/v1/reports/verify/{token}` porte le jeton dans le
**chemin** de l'URL. `ObservabilityMiddleware` journalise `request.url.path` à
l'entrée **et** à la sortie. Le jeton n'expire jamais et n'est pas révocable
indépendamment du compte rendu.

**Preuve.** Sonde sentinelle : la valeur placée dans le chemin est **retrouvée**
dans le journal applicatif — `log-sentinel-observations.json`, sentinelle
`jeton_verification`, surface `journal_application`.

**Portée réelle.** Ce que le jeton ouvre est borné : la réponse ne contient
aucune identité patient ni valeur biologique, seulement statut, identifiants
techniques, version, empreinte du PDF et dates. Quiconque lit les journaux du
conteneur obtient donc la capacité de confirmer l'existence et l'état d'un
compte rendu, indéfiniment et sans limite de rejeu. Ce n'est pas une fuite de
donnée de santé ; c'en est une de capacité d'accès.

**Remédiation : lot D.**

### B-08 — L'application s'écarte de la séparation des tâches attendue

**Constat.** 3 sondes sur 99 montrent un comportement différent de ce que la
séparation des tâches laisserait attendre. `expected` exprime la **règle métier
attendue**, pas ce que le code fait : un écart décrit donc l'application telle
qu'elle est, et non une sonde défaillante.

| Sonde | Observé | Attendu |
| --- | --- | --- |
| `accountant` → `POST /api/v1/aes` | **HTTP 201** | DENY — déclaration d'accident d'exposition au sang (statut sérologique) par le comptable |
| `technician` → `POST /api/v1/billing/calculate` | **HTTP 200** | DENY — calcul de facturation par un technicien |
| `accountant` → `POST /api/v1/quality/non-conformities` | **HTTP 201** | DENY — création d'une non-conformité qualité par le comptable |

**Preuve.** Sondes exécutées contre l'application, avec des jetons réels émis
pour des comptes synthétiques. Voir `rbac-matrix.json`, `runtime_probes`.

**Lien avec B-01.** Ces trois routes appartiennent aux 51 opérations à
authentification seule : l'écart est la conséquence directe de l'absence de
garde, pas un défaut distinct.

**Remédiation : lot D.**

### B-09 — Des données patient synthétiques apparaissent hors de l'audit métier

**Constat.** Des sentinelles ont été retrouvées dans des surfaces techniques :
le **journal applicatif** (code-barres, jeton de vérification) et les **messages
d'erreur renvoyés au client** (IPP, prénom, code-barres).

**Preuve.** `log-sentinel-observations.json` — 70 observations, 6 sentinelles
retrouvées sur 3 surfaces.

**Ce que ce constat ne dit pas.** L'IPP retrouvé dans l'**audit métier en base**
n'est pas une fuite : c'est la fonction de la piste d'audit. Aucune sentinelle
n'atteint les métriques Prometheus ni leurs étiquettes — point positif, et
mesuré. Nom, date de naissance, téléphone, quartier, analyte et valeur de
résultat n'ont été retrouvés nulle part.

**Remédiation : lot D.**

### B-10 — La recherche de secrets de la CI était décorative

**Constat.** Le contrôle de secrets était déclaré `continue-on-error: true`,
donc incapable de bloquer quoi que ce soit. Exécuté tel quel, il **échoue déjà**
sur l'arbre courant : `.secrets.baseline` couvre 14 fichiers, alors que le scan
en relève dans bien davantage. L'échec était avalé, et personne n'en était
averti. L'historique Git n'était **pas scanné du tout** : un secret retiré de
l'arbre reste lisible dans l'objet Git qui le portait.

**Preuve.** Exécution de `python -m detect_secrets.pre_commit_hook --baseline
.secrets.baseline $(git ls-files)` : code de sortie 1. Chiffres exacts et
répartition par règle : [`SECRET_SCANNING.md`](SECRET_SCANNING.md) §6.

**Ce que le lot B a fait.** Il a rendu la barrière bloquante, ajouté le scan
d'historique avec un outil épinglé par version et empreinte, et documenté chaque
exception par empreinte, chemin, commit et justification. Il n'a **pas** réécrit
`.secrets.baseline` ni retiré quoi que ce soit de l'historique.

**Remédiation résiduelle : lot D** — nettoyage éventuel de `.secrets.baseline`.

## 4. Constats P2

### B-02 — Le modèle `military_facilities` n'a aucune table dans la base migrée

`app/models/ruggylab_os.py` définit `MilitaryFacility` avec **latitude et
longitude** d'établissements de santé militaires. La table `military_facilities`
est **absente** des 49 tables introspectées sur une base réellement migrée.
`GET /api/v1/military-facilities` ne peut donc pas fonctionner sur PostgreSQL
migré.

**Preuve.** `artifacts/g0/schema.json` ne contient pas `military_facilities`.

C'est à double tranchant : la route ne fonctionne pas, donc les coordonnées ne
sortent pas ; mais un modèle qui décrit des coordonnées d'établissements
militaires existe dans le code, et une migration future les matérialiserait sans
que rien ne le signale. **Remédiation : lot D.**

### B-04 — Le WebSocket ne vérifie pas `auth_version`

`_authenticate_ws_token` décode le JWT et vérifie la denylist, mais ne compare
pas `ver` à `user.auth_version` — contrôle que `get_current_user` applique. Un
jeton émis avant une modification sensible du compte reste accepté sur le
WebSocket jusqu'à son échéance (60 minutes), alors qu'il est refusé sur l'API
HTTP.

**Preuve.** Lecture de `app/api/v1/endpoints/notifications.py` et de
`app/api/deps.py`. **Remédiation : lot D.**

### B-05 — Aucun journal d'accès au proxy

`deploy/Caddyfile` ne contient aucune directive `log`. Aucune trace des accès
externes n'existe au niveau du proxy : après incident, seule reste la vue
applicative, qui ne voit pas ce que le proxy a refusé.

**Preuve.** Lecture de `deploy/Caddyfile`, confirmée par la sonde sentinelle,
qui enregistre cette surface comme **non exercée** plutôt que comme propre.
**Remédiation : lot D.**

### B-06 — Aucune durée de conservation définie pour les données cliniques

Le dépôt ne définit de purge que pour les jetons — 7 jours après expiration.
**493 des 519 colonnes** n'ont aucune borne : ni les patients, ni les résultats,
ni les comptes rendus, ni l'audit, ni les dossiers d'accident d'exposition au
sang.

**Preuve.** `data-classification.json`, champ `retention` = `UNKNOWN`.
**Remédiation : lot D.**

### B-07 — Le cloisonnement par unité ne repose que sur le code applicatif

Le lot A a relevé **zéro politique RLS**. La sonde confirme que le cloisonnement
**fonctionne par l'API** : un technicien de l'unité A se voit refuser le patient
de l'unité B. Il disparaît pour tout accès direct à la base — sauvegarde
comprise, dont le dump n'est pas chiffré.

**Preuve.** Sonde `technician_unit_a` ; `artifacts/g0/schema.json`,
`rls_policies` vide. **Remédiation : lot D.**

### B-11 — `.secrets.baseline` est inutilisable sur un runner Linux

**13 des 14 clés** de `.secrets.baseline` portent des séparateurs Windows
(`tests\conftest.py`). Sur un runner Linux, `detect-secrets` produit
`tests/conftest.py` et ne retrouve jamais ces entrées : **aucune** exception de
la baseline ne s'applique en CI, et le crochet de pré-commit d'un développeur
sous Linux ou macOS remonte les mêmes détections que si le fichier était vide.

**Preuve.** `secret-scan-summary.json`, champ
`windows_style_paths_normalised` : 13 chemins.

**Ce que le lot B a fait.** La barrière normalise les séparateurs **à la
lecture** ; le fichier versionné n'est pas modifié. Cette compensation est
elle-même la preuve du défaut. **Remédiation : lot D.**

## 5. Limites de cette revue

- Les 168 opérations `STATIC_EXPLICIT` sont décrites par **lecture** des
  dépendances, non par expérience. Une garde écrite dans le corps d'une fonction
  et non déclarée comme dépendance n'apparaîtrait pas — une seule a été trouvée.
- Les sondes tournent sur **SQLite**, pas sur PostgreSQL.
- Une sentinelle non retrouvée ne prouve pas qu'une donnée ne fuit jamais : elle
  prouve qu'elle n'a pas fuité sur les chemins exercés.
- Le contenu réellement transmis par chaque notificateur sortant, et celui
  réellement mis en cache dans Valkey, n'ont pas été inventoriés champ par
  champ. Ils sont classés `A_QUALIFIER`, pas `NON_SENSIBLE`.
- Aucune revue de code manuelle exhaustive n'a été conduite : ce lot mesure des
  surfaces, il ne remplace pas un audit applicatif.
- Aucun test d'intrusion n'a été mené, et aucune conclusion ne peut être tirée
  sur la résistance du système à un attaquant actif.
