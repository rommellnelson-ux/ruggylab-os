# Composants tiers — notices et licences

**Les composants recensés ici ne sont PAS couverts par la
[RuggyLab Evaluation License 1.0](LICENSE.md).** Chacun reste soumis à sa propre
licence. En cas de contradiction, la licence du composant tiers prévaut pour ce
composant.

Les textes intégraux requis sont conservés dans
[`licenses/third-party/`](licenses/third-party/), copiés depuis les paquets et
images réellement distribués — jamais retéléchargés depuis une source non
officielle.

| | |
| --- | --- |
| Version couverte | `0.8.0-beta.1` |
| Généré le | 2026-08-28 |
| SHA de génération | voir l'artefact CI `third-party-evidence` |
| Inventaire Python | `scripts/inventory_python_licenses.py` (`importlib.metadata`, sans outil tiers) |
| SBOM | Syft, version épinglée dans `.github/workflows/ci.yml` |
| Formats SBOM | CycloneDX JSON, SPDX JSON |

> **Cet inventaire n'est pas encore complet.** Les éléments du §6 bloquent la
> distribution externe tant qu'ils ne sont pas tranchés.

---

## 1. Dépendances Python directes

Les 20 dépendances déclarées dans `requirements.txt`. Ce sont elles qui entrent
dans l'image applicative.

| Paquet | Version | Licence | Obligation principale |
| --- | --- | --- | --- |
| fastapi | 0.136.3 | MIT | notice |
| starlette | 1.3.1 | BSD-3-Clause | notice |
| uvicorn[standard] | 0.49.0 | BSD-3-Clause | notice |
| pydantic-settings | 2.14.2 | MIT | notice |
| sqlalchemy | 2.0.50 | MIT | notice |
| **psycopg[binary]** | **3.3.4** | **LGPL-3.0-only** | **voir §5.3** |
| hl7 | 0.4.5 | BSD-3-Clause | notice |
| PyJWT[crypto] | 2.13.0 | MIT | notice |
| redis[hiredis] | 5.2.1 | MIT | notice — *client* Python, à ne pas confondre avec le serveur Redis (§6.1) |
| passlib | 1.7.4 | BSD-2-Clause | notice |
| python-multipart | 0.0.32 | Apache-2.0 | notice + NOTICE |
| alembic | 1.18.4 | MIT | notice |
| pytest | 9.0.3 | MIT | notice (test) |
| httpx | 0.28.1 | BSD-3-Clause | notice |
| onnxruntime | 1.26.0 | MIT | notice |
| Pillow | 12.3.0 | MIT-CMU | notice |
| numpy | 2.4.6 | BSD-3-Clause | notice |
| structlog | 26.1.0 | MIT OR Apache-2.0 | notice |
| prometheus-client | 0.25.0 | Apache-2.0 | notice + NOTICE |
| psutil | 7.2.2 | BSD-3-Clause | notice |

## 2. Dépendances transitives

L'inventaire exhaustif est produit par la CI à partir d'un **environnement
propre installé depuis `requirements.txt`**, et publié en artefact
(`python-licenses.json`).

> **Pourquoi un environnement propre est indispensable.** L'inventaire exécuté
> sur un poste de développement remontait 138 distributions, dont `pylint`
> (GPL-2.0-or-later), `pyinstaller` (GPL-2.0 avec exception) et `astroid`
> (LGPL-2.1-or-later). **Aucun de ces paquets n'est dans `requirements.txt`** :
> ce sont des outils de poste, absents de l'image distribuée. Les compter aurait
> fait apparaître un risque copyleft inexistant.

Répartition observée sur l'environnement complet, à titre indicatif : MIT (58),
Apache-2.0 (16), BSD-3-Clause (16), autres variantes BSD/MIT, LGPL-3.0 (2 —
psycopg et psycopg-binary). **0 licence indéterminée.**

**Mesure en environnement propre, exécutée en CI** (`run` 33184265952) :
**53 distributions**, dont **20 directes**, **0 licence indéterminée**. C'est
ce périmètre-là — et non celui du poste de développement — qui est distribué.

> **Le périmètre Python ne suffit pas.** L'image embarque en plus toute la base
> système. `scripts/audit_sbom_licenses.py` audite donc le SBOM de l'image
> elle-même : tout composant sans licence doit être qualifié par écrit dans
> `docs/governance/SBOM_LICENSE_EXCEPTIONS.json`, sinon la conformité échoue.
> Ce contrôle a fait apparaître l'élément traité au **§6.4**.

## 3. Images Docker

Les digests sont résolus par la CI au moment du build et publiés dans l'artefact
`third-party-evidence`. Un tag est mutable ; **seul le digest identifie
réellement l'image livrée**.

| Image | Tag | Rôle | Licence | Décision |
| --- | --- | --- | --- | --- |
| **`python`** | **`3.13-slim`** | base applicative | PSF-2.0 (Python) + **87 paquets Debian 13, majoritairement GPL/LGPL** | **REVUE OBLIGATOIRE — §6.4** |
| `caddy` | `2.8-alpine` | proxy TLS | Apache-2.0 | compatible — notice + NOTICE requis |
| `postgres` | `16.6-alpine` | base de données | PostgreSQL License (type BSD) | compatible — conteneur séparé, non modifié |
| **`redis`** | **`7.4-alpine`** | cache / files | **voir §6.1** | **REVUE OBLIGATOIRE** |
| `prom/prometheus` | `v3.1.0` | métriques | Apache-2.0 | compatible — notice + NOTICE requis |
| **`grafana/grafana`** | **`11.0.0`** | tableaux de bord | **AGPL-3.0** | **REVUE OBLIGATOIRE — §6.2** |

Aucune de ces images n'est modifiée : elles sont utilisées telles que publiées
par leurs éditeurs, dans des conteneurs séparés.

## 4. Ressources chargées à l'exécution depuis des CDN

Ces ressources ne sont **pas redistribuées** avec le logiciel : le navigateur les
récupère directement. Elles n'en font pas moins partie du produit, et certaines
portent des obligations d'attribution.

| Ressource | Version | Origine | Licence | Obligation |
| --- | --- | --- | --- | --- |
| Leaflet | 1.9.4 | cdnjs | BSD-2-Clause | attribution |
| JsBarcode | — | jsDelivr | MIT | attribution |
| Google Fonts | — | fonts.googleapis.com | dépend de la police (souvent OFL 1.1) | **à préciser** |
| Tuiles OpenStreetMap | — | tile.openstreetmap.org | données ODbL | attribution **présente** dans `ehm_map.html` ✓ + politique d'usage des tuiles |

> **Point d'exploitation, hors licence.** Ces quatre ressources créent une
> dépendance réseau sortante depuis le poste client. Dans un déploiement en
> environnement contraint ou hors ligne, la carte, les codes-barres et les
> polices ne s'afficheront pas. À traiter séparément si un fonctionnement
> déconnecté est visé.

## 5. Licences copyleft, source-available ou particulières

### 5.1 Apache-2.0 — `python-multipart`, `prometheus-client`, Caddy, Prometheus

Obligations : conserver la licence, les mentions de copyright et **le fichier
`NOTICE`** s'il existe ; signaler les modifications. Aucun de ces composants
n'est modifié. Compatible avec une distribution propriétaire.

### 5.2 MPL-2.0 — `certifi`, `pathspec` (transitifs)

Copyleft **par fichier**. Aucun fichier de ces paquets n'est modifié : aucune
obligation de divulgation ne naît. Conserver les licences.

### 5.3 LGPL-3.0 — `psycopg` et `psycopg-binary` (dépendance directe)

**Ce que la LGPL exige ici, et ce qu'elle n'exige pas.**

`psycopg` est utilisé **tel quel**, comme bibliothèque, sans modification et sans
liaison statique. Dans cette configuration, la LGPL-3.0 impose :

- de conserver la licence et les mentions de copyright ;
- d'**indiquer** que la bibliothèque est utilisée et sous quelle licence ;
- de permettre au destinataire de **remplacer** la bibliothèque par une version
  modifiée — satisfait ici, `psycopg` étant un paquet Python installé
  séparément, remplaçable dans l'environnement sans reconstruire RUGGYLAB OS.

**La LGPL ne rend pas RUGGYLAB OS open source.** Elle ne s'étend pas au code qui
se contente d'utiliser la bibliothèque. Cette précision figure ici parce que la
confusion entre LGPL et GPL est courante et conduirait à une conclusion fausse.

> `psycopg[binary]` embarque des binaires `libpq`, sous **PostgreSQL License**
> (type BSD, permissive). Leur licence est conservée dans
> `licenses/third-party/python/psycopg-binary/`.

## 6. Éléments non résolus — bloquants pour la distribution

### 6.1 Redis 7.4 — `MANUAL_LICENSE_REVIEW_REQUIRED`

**Aucune décision n'est prise ici, et aucune licence n'est choisie à la place du
titulaire.**

Redis a changé de licence à partir de la version 7.4 : il n'est plus distribué
sous BSD-3-Clause mais sous un **double régime source-available**, au choix du
destinataire, entre :

- **RSALv2** (Redis Source Available License v2) ;
- **SSPLv1** (Server Side Public License v1).

Ni l'une ni l'autre n'est une licence open source au sens de l'OSI. Ce qu'il
faut retenir pour une distribution :

- elles **restreignent** la fourniture de Redis « en tant que service » à des
  tiers ;
- la **SSPLv1** comporte une clause de divulgation étendue si le logiciel est
  proposé comme service ;
- un **usage interne** — cache d'une application déployée pour son propre compte
  — est le cas le moins contraignant, mais **redistribuer l'image** avec la pile
  n'est pas la même chose que l'exécuter.

**Options prudentes, à trancher par le titulaire :**

| Option | Ce qu'elle implique |
| --- | --- |
| A. Conserver Redis 7.4 | après lecture des conditions RSALv2/SSPLv1 et confirmation que l'usage projeté y satisfait |
| B. Version ou licence différente | par exemple une version antérieure encore sous BSD-3-Clause, avec vérification du support de sécurité |
| C. Alternative compatible | un cache sous licence permissive, au prix d'une migration et de tests |
| D. Exclure Redis de la distribution | ne pas livrer l'image ; l'exploitant fournit son propre Redis |

**Aucune de ces options n'est appliquée dans cette PR.** Remplacer ou rétrograder
Redis exigerait une décision distincte et une campagne de tests complète : le
cache porte les compteurs de rate-limiting, la file de trames automates et le
verrou de numérotation.

### 6.2 Grafana 11 — `AGPL_DISTRIBUTION_REVIEW_REQUIRED`

Grafana 11 est sous **AGPL-3.0**. Les obligations diffèrent radicalement selon
l'usage, et **aucune conclusion n'est tirée ici sans preuve écrite** :

| Situation | Obligation AGPL — à confirmer juridiquement |
| --- | --- |
| Conteneur séparé, **non modifié**, exécuté par l'exploitant pour son propre compte | usage, non distribution — l'AGPL n'impose alors rien de plus que le respect de la licence |
| **Distribution de la pile** incluant l'image Grafana | mise à disposition d'une œuvre AGPL : licence et source correspondante doivent être accessibles au destinataire |
| Grafana **modifié** (plugins, thèmes, patches) | les modifications relèvent de l'AGPL et doivent être publiées |
| Grafana **mis à disposition en réseau** à des tiers | clause réseau de l'AGPL : la source correspondante doit être offerte aux utilisateurs distants |

État constaté : Grafana est utilisé **non modifié**, dans un conteneur séparé,
avec des tableaux de bord provisionnés. Les tableaux de bord sont des **données
de configuration** propres au projet, pas des œuvres dérivées de Grafana.

Ce qui reste à trancher : la pile est-elle **distribuée** à des tiers, ou
seulement déployée par le titulaire ? La réponse détermine l'obligation, et elle
n'est pas technique.

### 6.3 Google Fonts — provenance à préciser

La ou les familles chargées depuis `fonts.googleapis.com` ne sont pas
identifiées dans cet inventaire. La plupart sont sous **OFL 1.1**, mais cela doit
être **vérifié police par police**, pas supposé.

### 6.4 Base Debian de l'image applicative — `BASE_IMAGE_SOURCE_OFFER_REVIEW_REQUIRED`

**Découvert par le SBOM, pas supposé.** Le SBOM CycloneDX de l'image
(`artifacts/sbom.cyclonedx.json`, artefact `third-party-evidence`) recense
**155 composants** hors entrées de fichier, dont **87 paquets Debian 13
« trixie »** hérités de `python:3.13-slim`. Le recensement des licences
copyleft, produit par `scripts/audit_sbom_licenses.py` :

| Famille | Occurrences relevées |
| --- | --- |
| GPL-2.0 (`-only` / `-or-later`) | 111 |
| GPL-3.0 (`-only` / `-or-later`) | 64 |
| LGPL-2.0 / 2.1 (`-only` / `-or-later`) | 92 |
| LGPL-3.0 (`-only` / `-or-later`) | 34 |
| GPL-1.0, GPL générique, exceptions de liaison | 29 |
| MPL-1.1 / MPL-2.0 | 3 |

Une même licence peut être comptée pour plusieurs paquets ; ces nombres
mesurent la présence, pas un nombre de composants distincts.

**Ce qui est démontré.** Deux constats, vérifiés dans l'image construite :

- les **87 fichiers `copyright` Debian sont présents** dans l'image
  (`/usr/share/doc/*/copyright`) ;
- les **textes de licence référencés sont présents** eux aussi
  (`/usr/share/common-licenses/` contient GPL-1, GPL-2, GPL-3, LGPL-2,
  LGPL-2.1, LGPL-3, MPL-1.1, MPL-2.0, Apache-2.0, BSD…), et 77 des
  87 fichiers `copyright` y renvoient.

L'obligation de **notice** est donc satisfaite par l'image elle-même.

**Ce qui n'est PAS résolu.** La GPL-2.0 (§3) et la GPL-3.0 (§6) attachent, à
qui **distribue** des binaires, une obligation d'**offre du code source
correspondant**. Publier l'image sur un registre accessible à des tiers est une
distribution. Trois voies existent — offre écrite valable trois ans, mise à
disposition depuis la même source, ou transmission de l'offre reçue de l'amont —
et **aucune n'est tranchée ici**. Il n'est conclu ni que l'obligation est
satisfaite, ni qu'elle est violée : elle n'a pas été instruite.

**Ce que cela ne veut pas dire.** La présence de paquets GPL dans l'image de
base **ne rend pas RUGGYLAB OS open source**. Ces paquets sont des programmes
séparés, non modifiés, exécutés comme tels ; RUGGYLAB OS ne les incorpore pas
dans son propre code.

**Conduite à tenir.** Marqueur `BASE_IMAGE_SOURCE_OFFER_REVIEW_REQUIRED`.
Bloquant pour toute **distribution externe** de l'image, sans effet sur l'usage
d'évaluation interne. Options à instruire, sans préférence exprimée ici :

| Option | Ce qu'elle implique |
| --- | --- |
| A. Offre écrite de source | rédiger et honorer une offre valable trois ans pour les composants GPL de la base |
| B. Renvoi à l'amont Debian | s'appuyer sur les sources publiées par Debian ; à confirmer par écrit, ce n'est pas automatique |
| C. Base à empreinte réduite | réduire la surface copyleft ; décision d'ingénierie distincte, avec tests complets |
| D. Pas de distribution externe de l'image | statu quo actuel : l'image reste interne |

## 7. Éléments explicitement absents de la distribution

Vérifié dans cette PR :

| Élément | Constat |
| --- | --- |
| Modèle IA paludisme (`models/malaria_mobilenetv2`) | **absent du dépôt** ; l'inférence clinique reste désactivée. Aucun poids n'est distribué, donc aucune licence de modèle à qualifier. |
| Valeurs de référence biologiques | la migration crée le **schéma seul** ; **aucune valeur n'est embarquée**. La mention « IFCC/Tietz/OMS » décrit les sources qu'un exploitant peut renseigner — aucun contenu sous droit d'auteur n'est redistribué. |
| Polices embarquées | aucune. |
| Bibliothèques JS/CSS vendorisées | aucune ; tout est chargé depuis un CDN (§4). |
| Images | un seul fichier, `app/static/branding/RuggyLab_OS.jpg`, création du projet. |

> Si un modèle IA venait à être ajouté, sa licence, sa provenance et ses données
> d'entraînement devraient être qualifiées **avant** toute distribution. Un poids
> sans provenance démontrable doit être exclu.

## 8. Statut

| Statut | Valeur |
| --- | --- |
| `THIRD_PARTY_NOTICES_GENERATED` | ✅ |
| Licences indéterminées | **0** |
| Composants du SBOM d'image sans licence, non qualifiés | **0** |
| Exceptions qualifiées au registre | **4** — `SBOM_LICENSE_EXCEPTIONS.json` |
| `THIRD_PARTY_LICENSES_QUALIFIED` | ❌ — §6.1, §6.2, §6.3, §6.4 ouverts |
| Effet | **la distribution externe reste bloquée** |

Les quatre éléments ouverts bloquent la **distribution externe**. Aucun ne
bloque l'usage d'évaluation interne sur données fictives, qui est le seul usage
autorisé par la licence à ce stade.
