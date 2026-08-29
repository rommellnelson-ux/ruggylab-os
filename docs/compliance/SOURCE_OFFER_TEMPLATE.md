# Offre de code source correspondant — MODÈLE

> **MODÈLE — NON SIGNÉ, NON DÉLIVRÉ, NON RETENU.**
>
> Ce document n'est pas une offre. Il en est la forme, préparée pour que la
> décision puisse être prise en connaissance de cause. Il ne produit aucun effet
> tant qu'il n'a pas été **validé par un juriste**, complété, daté et signé par
> le Titulaire. **Aucun champ de signature ne doit être pré-rempli.**
>
> L'offre écrite est la **forme C** parmi quatre présentées dans
> [`SOURCE_COMPLIANCE.md`](SOURCE_COMPLIANCE.md) §5. Aucune n'est retenue à ce
> jour. Utiliser ce modèle ne vaut pas choix de cette forme.

---

## 1. Émetteur

| Champ | Valeur |
| --- | --- |
| Émetteur de l'offre | *(à compléter — personne ou entité qui distribue l'image)* |
| Adresse de contact pour les demandes | *(à compléter)* |
| Date d'émission | *(à compléter)* |

## 2. Objet

Cette offre porte sur le **code source correspondant** des composants logiciels
sous licence **GPL** ou **LGPL** contenus dans l'image :

| Champ | Valeur |
| --- | --- |
| Image | *(à compléter — référence complète)* |
| Digest | *(à compléter — `sha256:…`, seule référence immuable)* |
| Version RUGGYLAB OS | *(à compléter)* |
| Base | `python:3.13.15-slim-trixie` — Debian GNU/Linux 13 « trixie » |
| Nombre de paquets binaires concernés | *(à compléter depuis `debian-license-manifest.json`)* |
| Nombre de paquets sources correspondants | *(à compléter depuis `debian-source-packages.json`)* |

Le périmètre exact — chaque paquet, chaque version, chaque source — est celui du
manifeste joint, généré depuis l'image portant le digest ci-dessus. **Une offre
qui ne désigne pas un digest ne désigne rien** : un tag peut changer de contenu.

## 3. Ce qui est offert

L'émetteur s'engage à fournir, à toute personne ayant reçu l'image désignée
au §2, une copie complète et lisible par machine du code source correspondant
aux composants GPL et LGPL qu'elle contient, ainsi que les scripts nécessaires à
leur compilation et à leur installation.

Le code source correspond **exactement** aux versions binaires distribuées, à
l'identique de celles inscrites au manifeste.

## 4. Durée

| Champ | Valeur |
| --- | --- |
| Durée de l'engagement | *(à compléter — au moins celle exigée par la licence applicable)* |
| Point de départ | date de la dernière distribution de l'image désignée |

> **Point à faire trancher.** La GPL-2.0 §3(b) exige une offre valable **au
> moins trois ans**. La GPL-3.0 §6(b) exige qu'elle vaille **au moins trois ans
> ou aussi longtemps que des pièces de rechange ou un support sont proposés**
> pour le produit. L'image contient des composants sous les deux régimes : la
> durée retenue doit satisfaire **la plus exigeante des deux**, et cette
> détermination n'est pas faite ici.

## 5. Modalités de la demande

| Champ | Valeur |
| --- | --- |
| Canal de demande | *(à compléter)* |
| Éléments à fournir par le demandeur | référence de l'image et digest reçus |
| Délai de réponse | *(à compléter)* |
| Support de livraison | *(à compléter — téléchargement, support physique…)* |
| Frais | *(à compléter — la licence n'autorise qu'un coût raisonnable de mise à disposition)* |

## 6. Ce que cette offre ne couvre pas

- **Le code de RUGGYLAB OS**, qui n'est pas sous GPL. Il reste régi par la
  RuggyLab Evaluation License 1.0. Les paquets Debian sont des programmes
  séparés, non modifiés, exécutés comme tels : leur présence dans l'image
  **n'entraîne aucune obligation d'ouverture du code de RUGGYLAB OS**.
- Les composants sous licences **permissives** (MIT, BSD, Apache-2.0…), dont les
  obligations sont de notice et non de source.
- Les composants **tiers exécutés séparément** par l'exploitant, notamment
  l'overlay de supervision optionnel.

## 7. Validation requise avant délivrance

Cette offre ne peut être délivrée qu'après :

- [ ] validation du texte par un juriste ;
- [ ] détermination de la durée applicable (§4) ;
- [ ] vérification que le mécanisme de livraison choisi est effectivement en
      place et tenable pour toute la durée de l'engagement ;
- [ ] génération du manifeste depuis l'image réellement publiée, et non depuis
      une image de préparation ;
- [ ] décision explicite du Titulaire retenant la forme C parmi celles du §5 de
      `SOURCE_COMPLIANCE.md`.

## 8. Signature

*Aucune ligne ci-dessous ne doit être pré-remplie.*

**Émetteur de l'offre**

```
Nom :
Qualité :
Date :
Signature :
```

**Relecture juridique**

```
Nom :
Qualité :
Date :
Signature :
```

---

**Tant que ce document n'est pas validé et signé, aucune offre n'est faite, et
la distribution externe de l'image reste bloquée.**
