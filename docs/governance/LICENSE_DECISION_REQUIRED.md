# `LICENSE_DECISION_REQUIRED` — décision de licence à prendre avant le tag

> ## ✅ Mise à jour du 2026-08-28 — décision de principe PRISE
>
> Le titulaire a retenu une **licence propriétaire d'évaluation** :
> **RuggyLab Evaluation License 1.0** (`LicenseRef-RuggyLab-Evaluation-1.0`).
> Voir [`LICENSE_DECISION_BETA_2026-08-28.md`](LICENSE_DECISION_BETA_2026-08-28.md)
> et [`../../LICENSE.md`](../../LICENSE.md). Les quatre déclarations du dépôt
> sont alignées et verrouillées par un test.
>
> **Ce document reste néanmoins ouvert.** Deux points demeurent :
>
> 1. **Texte contractuel externe non validé.** Les clauses du §12 de la licence
>    — droit applicable, juridiction, durée, limitation de responsabilité,
>    règlement des litiges — exigent une **validation juridique** avant toute
>    distribution à un tiers extérieur.
> 2. **Composants tiers non entièrement qualifiés.** Voir
>    [`../../THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) : certains
>    composants restent en revue obligatoire et bloquent la distribution.
>
> Le constat initial ci-dessous est **conservé tel quel**, à titre historique :
> il décrit fidèlement l'état antérieur à la décision.

---

- **Date du constat** : 2026-08-28
- **Statut initial** : **bloquant pour `v0.8.0-beta.1`**
- **Décideur** : le propriétaire du dépôt. Ce point n'est pas technique.

## Le constat

RuggyLab OS **déclare** être sous GPL-2.0 à trois endroits :

| Emplacement | Déclaration |
| --- | --- |
| `pyproject.toml` | `"License :: OSI Approved :: GNU General Public License v2 (GPLv2)"` |
| `Dockerfile` | `org.opencontainers.image.licenses="GPL-2.0"` |
| `README.md` | badge `license-GPL--2.0` |

Mais **le dépôt ne contient aucun fichier `LICENSE`**, et l'historique Git ne
porte aucun commit de décision sur ce point.

## Pourquoi cela bloque le tag

Un tag publie une **GitHub Release** et une **image Docker** — deux actes de
distribution. Distribuer en annonçant une licence dont le texte est absent
laisse les destinataires sans conditions d'usage opposables : ni eux ni vous ne
savez ce qui est permis.

Le problème n'est pas cosmétique. **La GPL-2.0 est une licence copyleft** : elle
oblige quiconque distribue le logiciel, ou un dérivé, à en fournir le code
source sous la même licence. Pour un projet lié à une activité de laboratoire
privée, c'est une décision aux effets commerciaux durables — pas un fichier à
ajouter par commodité.

**Je n'ai donc pas ajouté de fichier `LICENSE`.** Choisir une licence engage le
propriétaire du code ; ce n'est pas à l'outillage de le faire à sa place.

## Les options

### A — Confirmer la GPL-2.0

Ajouter le texte officiel de la GPL-2.0 dans `LICENSE`. Les trois déclarations
existantes deviennent alors exactes. **À mesurer** : tout tiers recevant l'image
Docker peut exiger le code source, et un dérivé propriétaire devient impossible.

### B — Choisir une autre licence

Mettre à jour les trois déclarations en conséquence. Quelques repères, sans
recommandation de ma part — ce choix vous appartient :

- **Propriétaire / tous droits réservés** : cohérent avec une exploitation
  commerciale ; supprimer alors le classifier OSI, le label OCI et le badge.
- **Permissive (MIT, Apache-2.0)** : réutilisation large sans obligation de
  réciprocité ; Apache-2.0 ajoute une clause de brevets.
- **AGPL-3.0** : copyleft étendu à l'usage en réseau — pertinent pour un logiciel
  servi en SaaS, contraignant pour un déploiement chez des tiers.

### C — Repousser la décision

Retirer les trois déclarations et indiquer explicitement que la licence n'est pas
arrêtée. **Le dépôt est public** : sans licence, le droit d'auteur par défaut
s'applique et personne n'a le droit de réutiliser le code — ce qui est une
position tenable, à condition qu'elle soit assumée et écrite, pas subie.

## Ce qui débloque le tag

Une seule de ces trois options, **mise en œuvre de façon cohérente** :
`LICENSE`, `pyproject.toml`, `Dockerfile` et `README.md` doivent dire la même
chose. Tant que ce n'est pas le cas, `v0.8.0-beta.1` ne doit pas être taggée.

> Ce document constate un état et présente des options. Il ne choisit rien et ne
> constitue pas un conseil juridique.
