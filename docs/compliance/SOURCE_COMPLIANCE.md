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

Chacun porte un **en-tête de provenance** : version du générateur, horodatage
UTC, commit Git, référence et identifiant de l'image, référence et digest de la
base, plateforme, architecture, distribution. Sans lui, un manifeste est
ininterprétable — on ignore de quelle image et de quelle architecture il parle,
et deux manifestes de plateformes différentes se confondraient.

| Fichier | Contenu |
| --- | --- |
| `artifacts/debian-binary-packages.json` | 87 paquets binaires : nom, version, architecture, paquet source, version source, taille |
| `artifacts/debian-source-packages.json` | 61 paquets sources : binaires produits, familles de licences, **fichiers sources exacts** avec URL, taille et SHA-256, disponibilité constatée |
| `artifacts/debian-license-manifest.json` | par paquet : licences déclarées, **famille**, fichier `copyright`, textes référencés, textes manquants |

### Ce que les preuves établissent

| Constat | Valeur |
| --- | --- |
| Plateforme décrite | `linux/amd64` — Debian GNU/Linux 13 « trixie » |
| Paquets binaires Debian dans l'image | **87** |
| Paquets sources correspondants | **61** |
| Paquets binaires où une **famille copyleft est détectée** | **76** |
| Paquets **sans** fichier `copyright` dans l'image | **0** |
| Textes de licence référencés et manquants, non qualifiés | **0** |
| **Paquets sources vérifiés disponibles** | **61 / 61** |
| **Fichiers sources résolus** (`.dsc`, `.orig.tar.*`, `.debian.tar.*`…) | **194** |
| **Fichiers sources vérifiés joignables** | **194 / 194** |
| **Fichiers sans SHA-256 attendu** | **0** |

Ces lignes ne sont pas des affirmations. Chaque URL a été **interrogée**, chaque
`.dsc` **téléchargé**, et les SHA-256 des archives proviennent du bloc
`Checksums-Sha256` que **Debian** y déclare — aucune valeur n'est inventée ni
recalculée en silence. Le SHA-256 du `.dsc` lui-même est, lui, calculé sur le
fichier reçu, et le manifeste le dit (`sha256_source`).

> **Un cas instructif, et la raison de ne pas se contenter d'un HTTP 200.**
> `debianutils` est publié via *dgit* : l'archive contient un fichier
> `debianutils_5.23.2.git.tar.xz` que le `.dsc` **ne référence pas** dans ses
> `Checksums-Sha256`. Ce n'est pas un hash manquant — c'est un fichier qui ne
> fait pas partie du source correspondant déclaré par Debian. Le manifeste le
> range donc sous `related_archive_files`, avec le motif. Le compter comme
> source aurait produit un faux défaut ; lui inventer un hash aurait été pire.

### Familles de licences détectées

Le générateur classe chaque expression de licence en famille : `GPL`, `LGPL`,
`AGPL`, `MPL`, `EPL`, `CDDL`, `PERMISSIVE` ou `UNKNOWN`. Une licence non
reconnue est marquée `UNKNOWN` plutôt que rangée par défaut du côté rassurant.

> **Cette classification est un signal de revue, pas une qualification
> juridique.** Les familles copyleft **n'imposent pas la même forme** de mise à
> disposition : la portée de la MPL est le *fichier*, celle de la GPL l'*œuvre*,
> celle de l'AGPL s'étend à l'*usage en réseau*, et la LGPL distingue le lien de
> la dérivation. Les regrouper sous une conclusion unique serait faux. Le
> manifeste porte donc `copyleft_detected`, `license_family` et
> `source_compliance_review_required` — jamais une obligation affirmée — et
> `written_offer_applicability` vaut invariablement `LEGAL_REVIEW_REQUIRED`.

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
RELEASE_PIPELINE_SOURCE_EVIDENCE_GATED ✅ `deploy` dépend du job de preuves
LEGAL_SOURCE_OFFER_REVIEW_REQUIRED    ⛔ bloquant pour la distribution externe
```

Le job `debian-source-evidence` figure dans les `needs` de `deploy` : aucune
image ne peut être publiée sans que les preuves aient été produites et
vérifiées. Un job qui produit des preuves sans rien bloquer serait décoratif.
`monitoring-overlay` n'y figure pas et ne doit pas y figurer — Grafana est
externe, et un cœur sain ne dépend pas d'un composant que RUGGYLAB ne
distribue pas.

Ces deux statuts coexistent : les preuves sont prêtes, la décision ne l'est pas.
L'usage d'évaluation interne, seul autorisé à ce stade, n'est pas concerné.

## 8. À refaire à chaque changement de base

- [ ] relever le nouveau digest et mettre à jour le `Dockerfile` ;
- [ ] régénérer les trois manifestes depuis l'image reconstruite ;
- [ ] relancer `--check-availability` : les versions changent, les URL aussi ;
- [ ] mettre à jour les chiffres du §3 et la date du §2 ;
- [ ] réexaminer le registre des défauts de notice.
