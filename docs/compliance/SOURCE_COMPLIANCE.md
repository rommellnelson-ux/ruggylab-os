# Code source correspondant — composants GPL/LGPL de l'image de base

> **Ce document ne déclare aucune conformité.** Il rassemble les **preuves**
> nécessaires pour instruire la question, et énonce ce qui reste à trancher par
> un juriste. Statut maximal atteignable ici :
> `BASE_IMAGE_SOURCE_EVIDENCE_PREPARED` + `LEGAL_SOURCE_OFFER_REVIEW_REQUIRED`.

## 1. De quoi il s'agit

Distribuer une image Docker, c'est distribuer les binaires qu'elle contient.
L'image applicative de RUGGYLAB OS est construite sur `python:3.13.15-slim-trixie`,
qui embarque une base Debian 13. Une partie de ces paquets est sous **GPL** ou
**LGPL**, licences qui attachent à toute distribution de binaires une obligation
d'**offre du code source correspondant** — GPL-2.0 §3, GPL-3.0 §6.

Cette obligation **ne concerne pas le code de RUGGYLAB OS**. Les paquets Debian
sont des programmes séparés, non modifiés, exécutés comme tels. Rien de ce qui
suit ne rend RUGGYLAB OS open source.

## 2. Base épinglée

| Champ | Valeur |
| --- | --- |
| Image | `python` |
| Tag | `3.13.15-slim-trixie` |
| Digest | `sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f` |
| Distribution | Debian GNU/Linux 13 « trixie » |
| Date de relevé | 2026-08-28 |

Le `Dockerfile` référence désormais la base **par version exacte et par digest**,
dans ses deux étapes. `3.13-slim` était un tag **flottant** : il suit les
correctifs et change de contenu sans prévenir. Une release construite dessus
n'est pas reproductible, et les preuves rassemblées ici ne décriraient plus
l'image livrée.

## 3. Preuves produites

Générées par [`../../scripts/debian_source_manifest.py`](../../scripts/debian_source_manifest.py),
**depuis l'image réellement construite** — jamais depuis un fichier de
configuration, jamais depuis une supposition.

| Fichier | Contenu |
| --- | --- |
| `artifacts/debian-binary-packages.json` | 87 paquets binaires : nom, version, architecture, paquet source, version source, taille |
| `artifacts/debian-source-packages.json` | 61 paquets sources : binaires produits, licences copyleft, URL de snapshot, disponibilité constatée |
| `artifacts/debian-license-manifest.json` | par paquet : licences déclarées, fichier `copyright`, textes référencés, textes manquants, obligation |

### Ce que les preuves établissent

| Constat | Valeur |
| --- | --- |
| Paquets binaires Debian dans l'image | **87** |
| Paquets sources correspondants | **61** |
| Paquets binaires portant une obligation de source | **76** |
| Paquets **sans** fichier `copyright` dans l'image | **0** |
| Textes de licence référencés et manquants, non qualifiés | **0** |
| **Sources vérifiées disponibles sur `snapshot.debian.org`** | **61 / 61** |

La dernière ligne n'est pas une affirmation : chaque URL a été **interrogée**
(`--check-availability`), et le code HTTP est inscrit dans le manifeste. Une URL
écrite dans un document ne prouve rien tant que personne ne l'a ouverte.

### Licences copyleft les plus représentées

| Licence | Paquets |
| --- | --- |
| GPL-2+ | 50 |
| GPL-2 | 31 |
| GPL-3+ | 24 |
| LGPL-2.1+ | 22 |
| LGPL-2+ | 20 |
| LGPL-3+ | 16 |

Un même paquet peut déclarer plusieurs licences ; ces nombres mesurent la
présence, pas des composants distincts.

## 4. Ce qui est déjà satisfait : la NOTICE

Vérifié dans l'image construite :

- les **87 fichiers `copyright`** sont présents sous `/usr/share/doc/*/copyright` ;
- les textes de licence référencés sont présents sous
  `/usr/share/common-licenses/` : `GPL`, `GPL-1`, `GPL-2`, `GPL-3`, `LGPL`,
  `LGPL-2`, `LGPL-2.1`, `LGPL-3`, `GFDL`, `GFDL-1.2`, `GFDL-1.3`, `MPL-1.1`,
  `MPL-2.0`, `Apache-2.0`, `Artistic`, `BSD`, `CC0-1.0`.

Un seul défaut est constaté, et il est qualifié par écrit dans
[`../governance/DEBIAN_NOTICE_EXCEPTIONS.json`](../governance/DEBIAN_NOTICE_EXCEPTIONS.json) :
le fichier `copyright` de **gzip** renvoie à `/usr/share/common-licenses/GFDL-3`,
un nom qui n'a jamais existé dans la nomenclature Debian. C'est un **pointeur
périmé du paquet amont**, non un texte réellement absent : la GFDL est disponible
sous `GFDL-1.3`, et elle couvre la *documentation* de gzip, dont le code est sous
GPL-3 — texte présent. Corriger ce pointeur reviendrait à modifier un paquet
Debian dans notre image, ce qui créerait une divergence plus gênante que le
défaut.

## 5. Ce qui n'est PAS satisfait : l'OFFRE DE SOURCE

**Rien de ce qui précède ne répond à l'obligation d'offre.** Elle reste entière,
et elle n'a pas été instruite.

Quatre formes ont été **préparées**, sans qu'aucune soit retenue ni déclarée
suffisante. Le choix relève du titulaire, après validation juridique.

| Forme | Ce qu'elle suppose | Ce qui plaide pour | Ce qui plaide contre |
| --- | --- | --- | --- |
| **A. Bundle des sources correspondantes** | télécharger et conserver les 61 paquets sources, les distribuer avec l'image | autonome, ne dépend d'aucun tiers | plusieurs Go, à régénérer à chaque changement de base |
| **B. Téléchargement reproductible depuis un snapshot immuable** | fournir le manifeste et un script tirant les sources de `snapshot.debian.org` | léger ; les 61 URL sont **vérifiées disponibles** | dépend de la pérennité d'un service tiers |
| **C. Offre écrite de source** | [`SOURCE_OFFER_TEMPLATE.md`](SOURCE_OFFER_TEMPLATE.md), valable la durée requise | forme classique, prévue par les licences | engage à honorer la demande pendant des années |
| **D. Conservation interne** | archiver sources et scripts de reconstruction, sans distribution externe | suffisant tant que rien n'est distribué | ne répond à rien dès qu'une distribution a lieu |

> **Une remarque, pas une conclusion.** La forme B s'appuie sur le fait que
> Debian publie elle-même les sources correspondantes. Certains considèrent que
> cela suffit ; d'autres estiment que celui qui distribue doit pouvoir fournir
> les sources lui-même, sans dépendre d'un tiers. **Ce point n'est pas tranché
> ici** et ne peut pas l'être sans avis juridique.

## 6. Ce que ce document ne dit pas

- Il **ne déclare pas** la distribution externe conforme.
- Il **ne conclut pas** qu'une forme d'offre est suffisante.
- Il **ne prétend pas** que Debian publiant les sources dispense le
  redistributeur de son obligation.
- Il **ne rend pas** RUGGYLAB OS open source, et rien dans la présence de
  paquets GPL dans une image de base n'y conduit.

## 7. Statut

```
BASE_IMAGE_SOURCE_EVIDENCE_PREPARED   ✅ preuves produites et vérifiées
LEGAL_SOURCE_OFFER_REVIEW_REQUIRED    ⛔ bloquant pour la distribution externe
```

Ces deux statuts coexistent : les preuves sont prêtes, la décision ne l'est pas.
L'usage d'évaluation interne, seul autorisé à ce stade, n'est pas concerné.

## 8. À refaire à chaque changement de base

- [ ] relever le nouveau digest et mettre à jour le `Dockerfile` ;
- [ ] régénérer les trois manifestes depuis l'image reconstruite ;
- [ ] relancer `--check-availability` : les versions changent, les URL aussi ;
- [ ] mettre à jour les chiffres du §3 et la date du §2 ;
- [ ] réexaminer le registre des défauts de notice.
