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

> **Cet inventaire n'est pas complet.** Les éléments du §6 restent ouverts et
> bloquent la distribution externe — laquelle est de toute façon verrouillée par
> [`DISTRIBUTION_STATUS`](docs/governance/DISTRIBUTION_STATUS) = `DISTRIBUTION_NO_GO`.

---

## 0. Ce que RUGGYLAB distribue, et ce qu'il ne fait que référencer

La distinction commande toute la suite. Une obligation de notice ou de source ne
naît que de ce qu'on **distribue** ; référencer une image que l'exploitant tire
lui-même n'est pas la distribuer.

### Distribué par RUGGYLAB

| Élément | Contenu |
| --- | --- |
| **Image applicative** `ghcr.io/<owner>/ruggylab-os` | code RUGGYLAB + dépendances Python + base Debian |
| Paquet Python (wheel / sdist) | code RUGGYLAB + textes de licence |
| Code source et documentation de la version | dépôt |
| Licences et notices | `LICENSE.md`, ce document, `licenses/third-party/` |
| SBOM | CycloneDX, SPDX |
| Manifestes Debian | binaires, sources, licences |

### Référencé dans Docker Compose, tiré par l'exploitant depuis l'amont

`caddy`, `postgres`, `valkey`, `prom/prometheus`. **RUGGYLAB ne les republie
pas** : le workflow ne pousse qu'une seule image, la sienne. Ces conteneurs sont
exécutés séparément, non modifiés, à partir des registres de leurs éditeurs.

### Intégration optionnelle externe

`grafana/grafana`, via `docker-compose.monitoring.yml` uniquement — voir §6.2.

> **Une distribution hors ligne changerait ce périmètre.** Regrouper les images
> tierces dans une archive livrée au client ferait de RUGGYLAB leur
> redistributeur, avec les obligations qui s'y attachent. Ce serait un
> changement de périmètre de conformité, et il exigerait un nouvel audit.

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

**Distribuée par RUGGYLAB — l'image applicative, et elle seule :**

| Élément | Valeur |
| --- | --- |
| Base | `python:3.13.15-slim-trixie` |
| Digest de la base | `sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f` |
| Distribution | Debian GNU/Linux 13 « trixie » |
| Licences | PSF-2.0 (CPython) + **87 paquets Debian**, dont une majorité de familles copyleft |
| Preuves | 61 paquets sources, **194 fichiers sources** avec URL et SHA-256 — voir §6.3 |

**Référencées dans Compose, tirées par l'exploitant :**

| Image | Tag | Rôle | Licence | Constat |
| --- | --- | --- | --- | --- |
| `caddy` | `2.8-alpine` | proxy TLS | Apache-2.0 | non modifiée, conteneur séparé, notice + NOTICE |
| `postgres` | `16.6-alpine` | base de données | PostgreSQL License (type BSD) | non modifiée, conteneur séparé |
| **`valkey/valkey`** | **`8.1.9-alpine`** (digest épinglé) | cache, files, verrous | **BSD-3-Clause** | non modifiée ; texte versionné par RUGGYLAB — voir §6.1 |
| `prom/prometheus` | `v3.1.0` | métriques | Apache-2.0 | non modifiée, conteneur séparé |

**Intégration optionnelle externe** — hors du cœur, voir §6.2 :

| Image | Tag | Licence | Où |
| --- | --- | --- | --- |
| `grafana/grafana` | `11.0.0` (digest épinglé) | **AGPL-3.0** | `docker-compose.monitoring.yml` seulement |

Aucune de ces images n'est modifiée, et **aucune n'est republiée par RUGGYLAB**.

## 4. Ressources chargées à l'exécution depuis des CDN

Ces ressources ne sont **pas redistribuées** avec le logiciel : le navigateur les
récupère directement. Elles n'en font pas moins partie du produit, et certaines
portent des obligations d'attribution.

| Ressource | Version | Origine | Licence | Obligation |
| --- | --- | --- | --- | --- |
| Leaflet | 1.9.4 | cdnjs | BSD-2-Clause | attribution |
| JsBarcode | — | jsDelivr | MIT | attribution |
| Tuiles OpenStreetMap | — | tile.openstreetmap.org | données ODbL | attribution **présente** dans `ehm_map.html` ✓ + politique d'usage des tuiles |

Ces ressources **ne sont pas embarquées dans l'image** : le navigateur du poste
client les récupère directement. RUGGYLAB ne les redistribue donc pas ; il les
référence, et leurs obligations sont d'attribution.

> **Google Fonts a été supprimé.** L'interface utilise désormais une **pile de
> polices système** — aucune police n'est téléchargée ni embarquée, et aucune
> licence de police n'est à qualifier. Un test interdit qu'un service de polices
> tiers réapparaisse, `@font-face` distante comprise.

> **Point d'exploitation, hors licence.** Les trois ressources restantes créent
> une dépendance réseau sortante depuis le poste client. En environnement
> contraint ou hors ligne, la carte et les codes-barres ne s'afficheront pas.
> L'interface, elle, reste lisible : les polices ne dépendent plus du réseau.

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

## 6. Composants qualifiés, et ce qui reste ouvert

Trois des quatre points ouverts au 2026-08-28 sont **résolus dans le code**, et
ne le sont que parce que le dépôt le démontre — chaque levée de marqueur ci-
dessous a été vérifiée sur l'arbre courant avant d'être écrite.

### 6.1 Valkey 8.1.9 — Redis 7.4 écarté ✅

Redis avait quitté BSD-3-Clause à partir de la 7.4 pour un double régime
source-available (RSALv2 / SSPLv1) restreignant la redistribution. Le titulaire
a décidé de l'écarter ; la migration est **faite et fusionnée**.

| | |
| --- | --- |
| Image | `valkey/valkey:8.1.9-alpine` |
| Digest | `sha256:e0eb7c480958d32bdc4357a74bdd70653ae15f2f9b4c93c4a5a9fad1dc471c84` |
| Licence | **BSD-3-Clause** — `COPYING` de `valkey-io/valkey` @ 8.1.9 |
| Texte versionné | [`licenses/third-party/containers/valkey/COPYING`](licenses/third-party/containers/valkey/COPYING) |
| Rôle | serveur de cache, files, verrous — service du cœur |
| Runtime | **vérifié** : 17 contrôles, dont `valkey_version = 8.1.9` lu sur le binaire et la persistance AOF après redémarrage |

**Le client Python ne change pas.** `redis-py` reste **MIT** : le changement de
licence de 2024 visait le *serveur*, pas ce client. Les URL gardent le schéma
`redis://`, qui nomme le protocole et non le produit.

**Constat signalé** : l'image Valkey **n'embarque pas** son texte de licence.
RUGGYLAB le versionne donc depuis la source officielle — sans quoi la notice ne
serait disponible nulle part côté exploitant.

> Marqueur `MANUAL_LICENSE_REVIEW_REQUIRED` **levé**. Vérifié sur l'arbre : plus
> aucune image serveur Redis dans les fichiers de distribution, et un test
> l'interdit.

### 6.2 Grafana 11 — hors du cœur distribué ✅

Grafana est sous **AGPL-3.0** et le reste : rien ici ne prétend le contraire. Ce
qui change, c'est que **RUGGYLAB ne le distribue pas**.

| | |
| --- | --- |
| Image | `grafana/grafana:11.0.0`, digest épinglé, **non modifiée** |
| Où | `docker-compose.monitoring.yml` **uniquement** |
| Qui la récupère | l'**exploitant**, directement depuis le registre de l'éditeur |
| Republication par RUGGYLAB | **aucune** — le workflow ne pousse que l'image applicative |
| Impact de son absence | **aucun** : le cœur est qualifié sans elle |

Le mode nominal supporté est **RUGGYLAB Core sans Grafana** : Prometheus reste
dans la stack principale et collecte `/metrics` directement, les tableaux de
bord métier sont intégrés à l'application. Son absence n'est pas un mode
dégradé — c'est le mode que le projet teste et supporte.

Les tableaux de bord provisionnés sont des **données de configuration** propres
au projet, montés en lecture seule ; ce ne sont pas des œuvres dérivées de
Grafana.

> Marqueur `AGPL_DISTRIBUTION_REVIEW_REQUIRED` **levé pour la distribution
> RUGGYLAB**, parce que la distribution n'a plus lieu. **L'AGPL continue de
> s'appliquer à Grafana lui-même**, entre son éditeur et l'exploitant qui
> l'exécute. Réintroduire Grafana dans le cœur, ou livrer une archive hors ligne
> le contenant, rouvrirait entièrement la question.

### 6.3 Google Fonts — supprimé ✅

La dépendance d'exécution à `fonts.googleapis.com` est **retirée**. L'interface
utilise une pile de polices système ; aucune police n'est téléchargée ni
embarquée, aucune licence de police n'est à qualifier. Vérifié dans un
navigateur : zéro requête vers un service de polices, zéro occurrence dans le
DOM rendu. Un test interdit la réapparition d'un service tiers, `@font-face`
distante comprise.

### 6.4 Sources correspondantes de la base Debian — **ouvert** ⛔

`LEGAL_SOURCE_OFFER_REVIEW_REQUIRED`

C'est le seul point de cette section qui reste ouvert, et il ne peut pas être
fermé par du code.

**Ce qui est démontré**, mesuré en CI sur l'image candidate
(`linux/amd64`, Debian 13) :

| Constat | Valeur |
| --- | --- |
| Paquets binaires Debian | **87** |
| Paquets sources correspondants | **61** |
| Paquets sources vérifiés disponibles | **61 / 61** |
| **Fichiers sources résolus** (`.dsc`, `.orig.tar.*`, `.debian.tar.*`…) | **194** |
| **Fichiers sources vérifiés joignables** | **194 / 194** |
| Fichiers sans SHA-256 attendu | **0** |
| Paquets sans fichier `copyright` | **0** |
| Textes de licence référencés manquants, non qualifiés | **0** |

Les SHA-256 des archives proviennent du bloc `Checksums-Sha256` que **Debian**
déclare dans le `.dsc` ; aucune valeur n'est inventée. Détail et méthode :
[`docs/compliance/SOURCE_COMPLIANCE.md`](docs/compliance/SOURCE_COMPLIANCE.md).

**Ce qui n'est pas résolu.** La forme de mise à disposition des sources n'a pas
été instruite. Les manifestes portent une terminologie **non conclusive** —
`copyleft_detected`, `license_family`, `source_compliance_review_required`, et
`written_offer_applicability = LEGAL_REVIEW_REQUIRED` — parce que
l'automatisation ne peut pas trancher : les familles copyleft **n'imposent pas
la même forme** de mise à disposition, la portée de la MPL étant le fichier,
celle de la GPL l'œuvre, celle de l'AGPL s'étendant à l'usage en réseau.

**Aucune des formes A, B, C ou D** de `SOURCE_COMPLIANCE.md` §5 n'est retenue.
**Aucun modèle n'est signé.** Il n'est conclu ni à la conformité, ni à la
non-conformité.

La présence de paquets GPL dans une base **ne rend pas RUGGYLAB OS open
source** : ce sont des programmes séparés, non modifiés, que RUGGYLAB
n'incorpore pas.

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
| Licences Python indéterminées | **0** |
| Composants du SBOM d'image sans licence, non qualifiés | **0** |
| Exceptions qualifiées au registre | **4** — `SBOM_LICENSE_EXCEPTIONS.json` |
| §6.1 Redis 7.4 → **Valkey 8.1.9** | ✅ fusionné, runtime vérifié |
| §6.2 Grafana → **hors du cœur distribué** | ✅ fusionné, cœur qualifié sans lui |
| §6.3 Google Fonts | ✅ **supprimé** |
| §6.4 Sources correspondantes Debian | ⛔ **`LEGAL_SOURCE_OFFER_REVIEW_REQUIRED`** |
| `THIRD_PARTY_LICENSES_QUALIFIED` | ❌ — §6.4 ouvert |
| Validation juridique du texte de `LICENSE.md` §12 | ⛔ **`LEGAL_LICENSE_REVIEW_REQUIRED`** |
| `DISTRIBUTION_STATUS` | **`DISTRIBUTION_NO_GO`** |

Trois des quatre points ouverts sont fermés **par le code**, et seulement parce
que le dépôt le démontre. Les deux qui restent — la forme de mise à disposition
des sources Debian, et la validation juridique du texte de licence — **ne
peuvent pas être fermés par du code**. Ils demandent un juriste et une décision
du titulaire.

Aucun de ces points ne bloque l'usage d'évaluation interne sur données
fictives, qui est le seul usage autorisé à ce stade.
