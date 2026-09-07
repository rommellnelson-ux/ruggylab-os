# Statut de distribution

Le fichier [`DISTRIBUTION_STATUS`](DISTRIBUTION_STATUS) contient la valeur
courante, lue par la CI. Ce document explique ce qu'elle verrouille, pourquoi
elle est **distincte** du statut clinique, et ce qu'il faudra pour la lever.

```
DISTRIBUTION_NO_GO
```

## 1. Deux verrous, deux questions

Confondre les deux ferait croire que lever l'un lève l'autre. Ce sont des
questions différentes, tranchées par des personnes différentes, sur des preuves
différentes.

| Fichier | Question | Interdit |
| --- | --- | --- |
| [`CLINICAL_STATUS`](CLINICAL_STATUS) → `REAL_DATA_NO_GO` | *Peut-on soigner avec ?* | usage sur données patient réelles, décision de soin, compte rendu remis |
| [`DISTRIBUTION_STATUS`](DISTRIBUTION_STATUS) → `DISTRIBUTION_NO_GO` | *Peut-on le remettre à quelqu'un ?* | publication de l'image, GitHub Release, remise à un tiers, **création du tag de version destiné à publier** |

Un logiciel peut être distribuable sans être clinique — c'est le cas d'une bêta
d'évaluation. Il peut aussi être cliniquement prêt sans être distribuable, si
ses obligations de licence ne sont pas satisfaites. **Aucun des deux statuts
n'implique l'autre.**

## 2. Ce que `DISTRIBUTION_NO_GO` interdit aujourd'hui

- publier l'image applicative sur GHCR ou tout autre registre ;
- créer une GitHub Release ;
- remettre l'image, le paquet ou l'archive à un tiers, quel qu'en soit le
  support ;
- **créer le tag** `v0.8.0-beta.1` — c'est le tag qui déclenche la publication,
  le bloquer en aval seulement laisserait une version taguée sans artefact,
  état bâtard dont personne ne veut.

Ce que ce statut **n'interdit pas** : construire, tester, qualifier, produire
des SBOM, et faire tourner la pile sur données synthétiques. Toute la CI
continue de s'exécuter.

## 3. Comment le verrou est appliqué

`tag-guard` lit ce fichier **avant** d'examiner la forme du tag. Une
pré-version parfaitement formée est refusée elle aussi :

```
statut de distribution : DISTRIBUTION_NO_GO
::error::Tag 'v0.8.0-beta.1' refusé : DISTRIBUTION_STATUS = DISTRIBUTION_NO_GO.
```

`deploy` ne s'exécute **que** sur un tag. Le chemin `workflow_dispatch` a été
retiré : il permettait de publier une image d'un simple clic, sans tag, donc
sans passer par `tag-guard` — le verrou aurait été contournable par
l'interface. `release` dépend de `deploy`. Aucun autre job ne pousse d'image ni
ne crée de Release, et un test le vérifie.

## 4. Ce qu'il faudra pour passer à `CONTROLLED_EVALUATION_DISTRIBUTION_GO`

Une **PR distincte**, une **décision humaine**, et les six preuves suivantes.
Aucune n'est acquise à ce jour.

| # | Preuve | État |
| --- | --- | --- |
| 1 | **Validation juridique du texte de licence** — clauses du §12 de [`../../LICENSE.md`](../../LICENSE.md) : droit applicable, juridiction, limitation de responsabilité, règlement des litiges | ⛔ non faite |
| 2 | **Choix du mécanisme de source Debian** — l'une des formes A à D de [`../compliance/SOURCE_COMPLIANCE.md`](../compliance/SOURCE_COMPLIANCE.md) §5, retenue et mise en œuvre | ⛔ aucune retenue |
| 3 | **Préflight dépôt privé terminé** — toutes les lignes de [`PRIVATE_REPOSITORY_PRE_TAG_CHECKLIST.md`](PRIVATE_REPOSITORY_PRE_TAG_CHECKLIST.md) cochées et datées | ⛔ aucune cochée |
| 4 | **Dépôt effectivement privé** | ⛔ public |
| 5 | **Protection de branche mise à jour** — voir [`BRANCH_PROTECTION_PRE_TAG_REQUIRED_CHECKS.md`](BRANCH_PROTECTION_PRE_TAG_REQUIRED_CHECKS.md) | ⛔ 2 checks requis sur 9 |
| 6 | **Autorisation explicite du titulaire**, écrite | ⛔ non délivrée |

## 5. Ce que ce document ne fait pas

Il **ne choisit pas** de forme d'offre de source, **ne valide rien
juridiquement**, et **ne préjuge pas** de la décision du titulaire. Il décrit un
verrou et ses conditions de levée — rien d'autre.
