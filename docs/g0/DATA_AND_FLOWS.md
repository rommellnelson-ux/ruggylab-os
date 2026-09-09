# G0 — Données sensibles, flux externes et sentinelles de journalisation

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

> **Classifier n'est pas protéger.** Ce document dit ce qu'une donnée *est* et
> qui l'atteint. Il n'empêche rien. Les acteurs ne sont pas affirmés : ils sont
> **calculés** depuis [`RBAC.md`](RBAC.md), par les routes qui servent chaque
> table.
>
> Généré par
> [`scripts/g0_security_baseline.py`](../../scripts/g0_security_baseline.py)
> depuis [`artifacts/g0/schema.json`](../../artifacts/g0/schema.json) — les
> colonnes réellement présentes dans une base migrée, jamais les modèles Python.
> Artefacts :
> [`data-classification.json`](../../artifacts/g0/data-classification.json),
> [`external-flows.json`](../../artifacts/g0/external-flows.json),
> [`log-sentinel-observations.json`](../../artifacts/g0/log-sentinel-observations.json).

## 1. Périmètre mesuré

| | |
| --- | --- |
| Colonnes classées | **519**, sur **49 tables** |
| Source des colonnes | introspection d'une base réellement migrée (lot A) |
| Acteurs par table | calculés depuis la matrice RBAC, pas déclarés |
| Tables sans route qui les serve | 3 — `alembic_version`, `csa_sync_state`, `report_delivery_outbox` |
| Frontières externes | **17** |
| Observations de sentinelles | **70** |

## 2. Classification des 519 colonnes

| Catégorie | Colonnes | Ce qu'elle recouvre |
| --- | ---: | --- |
| `TECHNIQUE` | **295** | Clés, horodatages de création, drapeaux, index métier. |
| `NON_SENSIBLE` | **86** | Libellés, unités, codes de nomenclature publics. |
| `AUDIT` | **35** | Auteur, date, motif d'une action tracée. |
| `IDENTITE` | **23** | IPP, nom, prénom, date de naissance, téléphone, quartier de résidence. |
| `FINANCIER` | **19** | Montants, échéances, paiements, tarifs. |
| `DONNEE_DE_SANTE` | **17** | Motif clinique, circonstances d'un accident d'exposition, examens demandés. |
| `A_QUALIFIER` | **16** | Champs libres dont le contenu réel n'est pas contraint par le schéma. |
| `RESULTAT_BIOLOGIQUE` | **13** | Valeurs, interprétations, instantanés de compte rendu. |
| `OPERATIONNEL_MILITAIRE` | **8** | Unité, grade, matricule, rattachement d'établissement. |
| `AUTHENTIFICATION_SECRET` | **7** | Empreintes de mots de passe, empreintes de jetons, secrets de notification. |

Niveau de risque attribué : **68** colonnes `ELEVE`, **70** `MOYEN`, **381**
`FAIBLE`.

`A_QUALIFIER` n'est pas une catégorie de confort : un champ texte libre comme
`aes_incidents.circumstances` peut contenir une identité et des éléments
cliniques sans que le schéma le dise. Le classer `NON_SENSIBLE` aurait été une
affirmation invérifiable.

### Où se concentrent les colonnes sensibles

| Catégorie | Tables concernées |
| --- | --- |
| `IDENTITE` | `patients` (7), `aes_incidents` (3), `epi_notifications` (3), `bnpl_schedules` (2), `invoices` (2), `users` (2), `exam_orders`, `notif_configs`, `qc_results`, `samples` |
| `DONNEE_DE_SANTE` | `aes_incidents` (5), `results` (3), `exam_order_items` (2), `exam_orders` (2), `invoice_lines` (2), `epi_notifications`, `malaria_analysis_jobs`, `samples` |
| `RESULTAT_BIOLOGIQUE` | `results` (9), `malaria_analysis_jobs` (2), `dh36_inbound_messages`, `report_snapshots` |
| `AUTHENTIFICATION_SECRET` | `users` (2), `dh36_inbound_messages`, `notif_configs`, `refresh_tokens`, `report_snapshots`, `revoked_tokens` |
| `OPERATIONNEL_MILITAIRE` | `equipments` (2), `patients` (2), `aes_incidents`, `exam_orders`, `invoices`, `users` |

`invoice_lines` porte deux colonnes classées `DONNEE_DE_SANTE` : une ligne de
facture nomme l'examen facturé. Une facture est donc aussi un document de santé,
et le cloisonnement clinique / gestion ne peut pas être obtenu en séparant
seulement les tables.

## 3. Chiffrement et conservation — ce qui a été observé

**Chiffrement en transit.** TLS existe entre le navigateur et le proxy Caddy, et
**seulement là**. Proxy → application, application → PostgreSQL et application →
Valkey circulent **en clair** sur le réseau Docker interne.

**Chiffrement au repos.** Aucun. Aucun chiffrement de colonne, aucun chiffrement
de volume, et le dump de sauvegarde n'est pas chiffré.

**Conservation.** **493 des 519 colonnes** n'ont **aucune durée de conservation
définie**. Le dépôt ne définit de purge que pour les jetons — 7 jours après
expiration. Aucune borne n'existe pour les patients, les résultats, les comptes
rendus, l'audit ou les dossiers d'accident d'exposition au sang. Constat
**B-06**, P2.

## 4. Les 17 frontières externes

12 sont actives par défaut ; 4 exigent une activation explicite ; l'overlay
Grafana n'est pas démarré par `docker-compose.yml`. Les données citées sont
celles qui **traversent** la frontière, pas celles que le système détient.

| Frontière | État par défaut | Catégories qui y circulent | Chiffrement | Risque résiduel mesuré |
| --- | --- | --- | --- | --- |
| Navigateur → proxy | actif | IDENTITE, SANTÉ, RÉSULTAT, FINANCIER, SECRET | TLS, autorité interne Caddy | **Aucun journal d'accès** : le `Caddyfile` ne contient pas de directive `log`. Après incident, rien à relire au niveau du proxy. |
| Proxy → application | actif | idem | **aucun**, HTTP en clair | Un conteneur compromis sur le même réseau lit le trafic, jetons compris, et joint `app:8000` directement — contournant les blocages `/metrics` et `/docs`. |
| Application → PostgreSQL | actif | **toutes** | aucun TLS observé | Un compte unique porte tous les droits ; **zéro politique RLS**. Le cloisonnement par unité vit dans le code applicatif : un accès direct à la base l'ignore. |
| Application → Valkey | actif si `CACHE_BACKEND=redis` | TECHNIQUE, `A_QUALIFIER` | aucun | Le contenu réellement mis en cache n'a pas été inventorié champ par champ. Classé `A_QUALIFIER`, pas `NON_SENSIBLE`. |
| Sauvegardes | actif | **toutes** | **aucun — dump non chiffré** | Une copie complète de la base — identités, résultats, sérologies — sur le même hôte. Qui accède au volume a tout, sans passer par aucune garde. |
| Exports CSV / PDF | actif | IDENTITE, SANTÉ, RÉSULTAT, FINANCIER, AUDIT | TLS en transit ; fichier déposé en clair | Le système perd la maîtrise à l'instant du téléchargement. Aucun filigrane, aucun marquage de destinataire, pas d'audit métier d'export sur toutes les routes. |
| Impression | actif, non instrumenté | IDENTITE, RÉSULTAT, FINANCIER | sans objet | Angle mort complet : l'application ne peut pas savoir qu'un document a été imprimé. |
| Journaux applicatifs | actif | TECHNIQUE, `A_QUALIFIER` | aucun | Le chemin de requête est journalisé tel quel — le jeton de vérification d'un compte rendu en fait partie (§5). |
| Prometheus | actif ; `/metrics` en 404 au proxy | TECHNIQUE | aucun | L'étiquette `endpoint` porte le **gabarit** de route, pas le chemin concret : aucun identifiant patient ne devient une étiquette. Vérifié par sentinelle. Le point reste joignable sans authentification depuis le réseau interne. |
| Grafana | overlay optionnel, jamais démarré | TECHNIQUE | aucun | Composant tiers hors périmètre distribué ; non audité par cette baseline. |
| CSA / Supabase | **désactivée** — `CSA_SYNC_ENABLED=false` | IDENTITE, SANTÉ, RÉSULTAT | TLS | Frontière la plus lourde : elle ferait sortir identités et résultats vers une plateforme tierce. Coupée par configuration ; cette baseline ne l'active pas. |
| ONMCI | activation requise, *fail-closed* | IDENTITE, SANTÉ | TLS | Sortie de données nominatives de santé vers un tiers institutionnel. |
| Webhooks sortants | selon configuration | `A_QUALIFIER`, RÉSULTAT | TLS | L'URL est choisie par un utilisateur autorisé : sortie de données pilotée par la configuration. Un transport anti-SSRF centralisé existe ; le contenu réellement transmis par chaque notificateur n'a pas été inventorié champ par champ. |
| Navigateur → CDN | actif | aucune donnée applicative | TLS | Code exécuté dans le navigateur fourni par un tiers ; sur un LAN sans Internet, la ressource ne charge pas. |
| Navigateur → tuiles OSM | actif | OPERATIONNEL_MILITAIRE (indirect) | TLS | Les coordonnées demandées révèlent au fournisseur de tuiles les zones consultées sur une carte d'établissements militaires. **À qualifier par l'autorité compétente.** |
| Automate DH36 / trames brutes | **désactivés** — `ENABLE_DH36_LISTENER=false`, `ANALYZER_RAW_LISTENER_ENABLED=false` | RÉSULTAT, TECHNIQUE | aucun | Si activée : frontière TCP non authentifiée et non chiffrée, trame brute conservée. Coupée par défaut. |
| Registres logiciels (build) | actif au build seulement | aucune donnée applicative | TLS | Chaîne d'approvisionnement ; atténuée par l'épinglage des actions par SHA et les SBOM du job de conformité. |

## 5. Sentinelles — ce que les journaux contiennent réellement

Dix valeurs synthétiques uniques, impossibles à confondre avec une donnée
réelle, ont été écrites par un parcours applicatif, puis **cherchées** dans sept
surfaces techniques. 70 observations, **6 sentinelles retrouvées**.

> Les valeurs des sentinelles ne figurent **pas** dans les artefacts : les y
> écrire les rendrait indétectables par un futur contrôle qui scannerait le
> dépôt lui-même.

| Sentinelle | Journal applicatif | Messages d'erreur client | Audit métier | Métriques | Étiquettes de métriques | Journal `scheduler` | Journal `analyzer-gateway` |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| IPP | — | **trouvée** | **trouvée** | — | — | — | — |
| Prénom | — | **trouvée** | — | — | — | — | — |
| Nom | — | — | — | — | — | — | — |
| Date de naissance | — | — | — | — | — | — | — |
| Téléphone | — | — | — | — | — | — | — |
| Quartier | — | — | — | — | — | — | — |
| Code-barres | **trouvée** | **trouvée** | — | — | — | — | — |
| Analyte | — | — | — | — | — | — | — |
| Valeur de résultat | — | — | — | — | — | — | — |
| Jeton de vérification | **trouvée** | — | — | — | — | — | — |

**Trois surfaces** portent au moins une sentinelle : le journal applicatif, les
messages d'erreur renvoyés au client, et l'audit métier en base.

Lecture :

- **L'audit métier en base porte l'IPP.** C'est sa fonction : tracer qui a fait
  quoi sur quel dossier. Ce n'est pas une fuite, c'est la piste d'audit.
- **Les messages d'erreur renvoyés au client** portent IPP, prénom et
  code-barres. Ils sont destinés à un appelant déjà authentifié, mais ils font
  sortir des identifiants du périmètre applicatif vers un client, un proxy et
  d'éventuels journaux intermédiaires.
- **Le journal applicatif** porte le code-barres et le **jeton de vérification
  d'un compte rendu**, tous deux parce qu'ils sont portés par le **chemin** de
  l'URL et que `ObservabilityMiddleware` journalise `request.url.path` à
  l'entrée et à la sortie. Constats **B-03** et **B-09**.
- **Les métriques Prometheus et leurs étiquettes ne portent aucune sentinelle.**
  Point positif, et mesuré : l'étiquette `endpoint` porte le gabarit de route.
- Nom, date de naissance, téléphone, quartier, analyte et valeur de résultat
  n'ont été retrouvés **nulle part**.

**Journal du proxy — surface non exercée.** `deploy/Caddyfile` ne contient
aucune directive `log` : le proxy n'écrit **aucun journal d'accès**. Il ne peut
donc pas divulguer de sentinelle, et il ne peut pas non plus servir à une
investigation. Constat **B-05**, P2.

Les constats **B-05**, **B-06** et **B-09** relèvent de ces mesures. Comme tous
les constats du lot B, ils sont transmis au **lot D** : rien n'est corrigé ici.

## 6. Ce que cette mesure ne prouve pas

- **Une sentinelle non retrouvée ne prouve pas qu'une donnée ne fuit jamais.**
  Elle prouve qu'elle n'a pas fuité *sur les chemins exercés*. Un chemin d'erreur
  non parcouru, une exception non déclenchée, un niveau de journalisation plus
  bavard en exploitation changeraient le résultat.
- Sept surfaces ont été examinées. Les journaux de PostgreSQL, ceux de Valkey et
  ceux du pilote Docker de l'hôte ne l'ont pas été.
- La classification des colonnes s'appuie sur le nom, le type et le contexte de
  la table. Un champ texte libre peut contenir davantage que ce que son nom
  annonce : c'est précisément pourquoi 16 colonnes restent `A_QUALIFIER`.
- Aucune donnée patient réelle n'a été utilisée, et aucune ne doit l'être tant
  que `CLINICAL_STATUS` vaut `REAL_DATA_NO_GO`.
