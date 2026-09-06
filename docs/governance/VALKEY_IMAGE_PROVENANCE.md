# Provenance de l'image Valkey

Fiche de vérification de l'image serveur qui remplace Redis 7.4.

## 1. Identification

| Champ | Valeur |
| --- | --- |
| Image | `valkey/valkey` |
| Tag | `8.1.9-alpine` |
| Digest | `sha256:e0eb7c480958d32bdc4357a74bdd70653ae15f2f9b4c93c4a5a9fad1dc471c84` |
| Licence | **BSD-3-Clause** |
| Source de la licence | `valkey-io/valkey`, fichier `COPYING` au tag `8.1.9` |
| Registre | Docker Hub — `docker.io/valkey/valkey` |
| Date de vérification | **2026-08-28** |
| Taille | ~16 Mo compressés |

Le service est référencé dans les fichiers Compose **par tag ET par digest**.
Un tag est mutable ; un digest ne l'est pas. Si l'éditeur republie
`8.1.9-alpine`, le déploiement échouera au lieu de tirer silencieusement un
contenu différent — c'est le comportement voulu.

## 2. Comment la vérification a été faite

1. `docker pull valkey/valkey:8.1.9-alpine` — le digest renvoyé par le registre
   est celui inscrit ci-dessus, confirmé par `docker image inspect`
   (`RepoDigests`).
2. `valkey-server --version` **exécuté dans l'image** renvoie
   `Valkey server v=8.1.9` : la version est celle du binaire, pas seulement
   celle du tag.
3. Le texte de licence a été récupéré depuis le dépôt officiel
   `valkey-io/valkey` au tag `8.1.9`, fichier `COPYING`, qui porte
   `SPDX-License-Identifier: BSD-3-Clause`. Il est versionné dans
   [`../../licenses/third-party/containers/valkey/COPYING`](../../licenses/third-party/containers/valkey/COPYING).

> **Constat à signaler.** L'image `valkey/valkey:8.1.9-alpine` **n'embarque pas**
> son propre texte de licence : une recherche de `LICENSE`/`COPYING` dans le
> système de fichiers du conteneur ne renvoie rien. Le texte est donc versionné
> **par RUGGYLAB**, depuis la source officielle. Sans cela, la notice ne serait
> disponible nulle part côté exploitant.

## 3. Pourquoi la 8.1 et non la 9.x

Valkey 9.1.1 existe et était disponible à la même date. La 8.1 a été retenue :

- elle correspond à la **même génération fonctionnelle** que Redis 7.4, qu'elle
  remplace ; la 9.x est une version majeure, avec les changements de
  comportement que cela suppose ;
- introduire une majeure inédite dans une pile qui porte le rate-limiting, la
  file de trames automates et le verrou de numérotation **ajouterait un risque
  sans bénéfice** pour une bêta dont l'objet est la qualification technique ;
- la 8.1.9 est le dernier correctif de sa ligne à la date de vérification.

Ce choix est révisable : passer en 9.x plus tard est une décision d'ingénierie
distincte, à instruire avec la même campagne de tests.

## 4. Ce que Valkey remplace, et ce qu'il ne remplace pas

| Élément | Avant | Après |
| --- | --- | --- |
| **Serveur** | `redis:7.4-alpine` — RSALv2/SSPLv1, source-available | `valkey/valkey:8.1.9-alpine` — BSD-3-Clause |
| **Client Python** | `redis-py` 5.2.1 — **MIT** | **inchangé** : `redis-py` 5.2.1, MIT |
| **Protocole** | RESP | **inchangé** |
| **Schéma d'URL** | `redis://` | **inchangé** — c'est le nom du protocole |
| **Code applicatif** | — | **aucun changement** : aucun nom d'hôte codé en dur |
| **Nom du service Compose** | `redis` | `valkey` |
| **Volume** | `redis_data` | `valkey_data` — **volume neuf**, voir le runbook |

`redis-py` est le **client du protocole**, publié sous licence MIT ; le
changement de licence de 2024 porte sur le **serveur** Redis, pas sur ce client.
Le conserver est donc sans difficulté de licence, et évite un changement
applicatif inutile.

## 5. Base Alpine de l'image

Comme toute image Alpine, `valkey/valkey:8.1.9-alpine` embarque `busybox`
(GPL-2.0) et `musl` (MIT). L'image est utilisée **telle que publiée par son
éditeur**, non modifiée, dans un conteneur séparé. Les obligations attachées à la
distribution éventuelle de cette image relèvent de la même analyse que celle
menée au §6.4 de [`../../THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)
pour la base Debian de l'image applicative. **Aucune conclusion n'est tirée ici.**

## 6. Vérification fonctionnelle contre le serveur réel

Exécutée le 2026-08-28 avec `redis-py` 5.2.1 contre
`valkey/valkey:8.1.9-alpine`, sur les primitives dont RUGGYLAB dépend
réellement — pas sur un simple `PING`.

| Contrôle | Résultat |
| --- | --- |
| `PING` | OK |
| Cache `SET`/`GET` avec TTL | OK |
| Expiration effective de la clé | OK |
| Compteur de rate limiting (`INCR` + `EXPIRE`) | OK |
| Quota par hash (`HINCRBY`) | OK |
| Denylist de jeton (`SETEX` + `EXISTS` + TTL) | OK |
| File de trames (`LPUSH` / `LTRIM` / `LLEN` / `RPOP`), ordre conservé | OK |
| Verrou distribué (`SET NX`), non réentrant | OK |
| Fan-out `PUBLISH`/`SUBSCRIBE` | OK |
| `BGREWRITEAOF` | OK |
| **Persistance après redémarrage du conteneur** | OK — clé et file retrouvées |

**16 contrôles sur 16.**

### Un point à connaître : la version annoncée

```
server_name    : valkey
valkey_version : 8.1.9
redis_version  : 7.2.4
```

Valkey annonce `redis_version: 7.2.4` dans `INFO server` : c'est la version de
**compatibilité protocolaire** qu'il déclare aux clients, pas sa propre version.
Un code qui déciderait d'un comportement à partir de `redis_version` verrait donc
7.2.4, et non 8.1.9.

Vérifié : **RUGGYLAB ne lit nulle part `redis_version`** ni `INFO server`. Aucun
comportement applicatif ne dépend de cette valeur. Le point est consigné parce
qu'il piégerait un développement futur, pas parce qu'il pose problème
aujourd'hui.

## 7. Ce qui reste à faire ailleurs

`THIRD_PARTY_NOTICES.md`, les SBOM, l'inventaire des images et le registre
`SBOM_LICENSE_EXCEPTIONS.json` **n'existent pas sur `main`** : ils sont portés
par la PR #142, encore ouverte. Les modifier ici créerait un conflit avec elle
sans rien apporter.

La requalification des notices — retrait de Redis 7.4, entrée Valkey, levée du
marqueur `MANUAL_LICENSE_REVIEW_REQUIRED` — se fera donc **dans la PR #142,
après fusion de la présente PR**, avec régénération des deux SBOM depuis l'image
réellement construite. Tant que cela n'est pas fait, le statut
`REDIS_REPLACED_BY_VALKEY` n'est pas prononcé.

Le texte de licence Valkey, lui, est versionné dès maintenant dans
`licenses/third-party/containers/valkey/` : c'est un ajout, il n'entre en
conflit avec rien.

## 6. À refaire à chaque changement de version

- [ ] `docker pull` et relevé du digest ;
- [ ] `valkey-server --version` dans l'image ;
- [ ] récupération du `COPYING` au tag correspondant et mise à jour du texte
      versionné ;
- [ ] mise à jour du tableau du §1 avec la nouvelle date de vérification ;
- [ ] campagne de tests complète (voir le runbook de migration).
