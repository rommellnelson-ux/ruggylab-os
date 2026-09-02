# Passage du dépôt en privé — vérifications avant tag

> **Décision prise** : `TARGET_REPOSITORY_VISIBILITY = PRIVATE_BEFORE_TAG`.
> Le dépôt passera en privé **avant** la création du tag `v0.8.0-beta.1`.
>
> **Ce document ne change rien.** Il énumère ce qui doit être vérifié, dans
> l'ordre, avant d'actionner le changement. La visibilité n'a pas été modifiée
> et ne doit pas l'être au titre de la présente préparation.

## Pourquoi cet ordre

Passer en privé n'est pas un simple réglage. Le changement touche la
disponibilité de l'intégration continue, l'analyse de sécurité, le registre
d'images et ce qui reste accessible aux tiers ayant déjà cloné ou forké. Créer
le tag d'abord publierait la version sous un régime que la décision écarte ;
changer la visibilité sans vérifier la CI risquerait d'obtenir un dépôt privé
dont le pipeline ne tourne plus, donc un tag qu'aucun gate ne protège.

**Aucun tag ne doit être créé tant que toutes les lignes ci-dessous ne sont pas
cochées et datées.**

---

## A. Préserver ce qui existe

| # | Vérification | Attendu | Fait le |
| --- | --- | --- | --- |
| A1 | **Bundle Git complet** produit hors du poste de travail | `git bundle create ruggylab-os-<date>.bundle --all` | |
| A2 | **Bundle vérifié** | `git bundle verify` sans erreur ; `git clone` du bundle dans un répertoire vierge, `git log` cohérent | |
| A3 | Bundle stocké sur un support distinct du poste et du dépôt | | |
| A4 | Toutes les branches locales et de travail poussées | `git push --all` contrôlé, aucun commit orphelin | |

Un dépôt public rendu privé reste récupérable par son propriétaire ; un dépôt
supprimé par erreur ne l'est pas. Le bundle protège contre la seconde
éventualité, pas la première.

## B. Ce qui reste accessible malgré le passage en privé

| # | Vérification | Attendu | Fait le |
| --- | --- | --- | --- |
| B1 | **Inventaire des forks publics existants** | liste exhaustive ; un fork déjà créé **ne devient pas privé** et conserve l'historique cloné | |
| B2 | Inventaire des clones connus hors GitHub | recensement déclaratif | |
| B3 | Contenu déjà indexé par des tiers (caches, moteurs, miroirs) | constat écrit — irréversible, à assumer, non à corriger | |

> **À écrire noir sur blanc.** Le passage en privé protège l'avenir, pas le
> passé. Tout ce qui a été publié pendant la période publique a pu être copié.
> C'est une raison de plus pour que le tag vienne **après**, pas avant.

## C. Accès

| # | Vérification | Attendu | Fait le |
| --- | --- | --- | --- |
| C1 | **Inventaire des collaborateurs** et de leurs droits | chaque compte justifié, droits au plus juste | |
| C2 | Équipes et accès par organisation | | |
| C3 | Clés de déploiement, jetons d'accès personnel, applications GitHub installées | recensés et justifiés | |
| C4 | **Règles de protection de branche** conservées après bascule | `main` protégée, checks requis inchangés | |

## D. Secrets

| # | Vérification | Attendu | Fait le |
| --- | --- | --- | --- |
| D1 | **Aucun secret dans l'historique** | analyse sur l'historique complet, pas seulement sur `HEAD` | |
| D2 | Secrets d'Actions recensés et rotés si exposés pendant la période publique | | |
| D3 | `.env` et fichiers dérivés absents du suivi Git | | |

> Passer en privé **ne neutralise pas** un secret déjà présent dans un commit
> public. Un secret exposé doit être **révoqué**, pas caché.

## E. Intégration continue et sécurité

| # | Vérification | Attendu | Fait le |
| --- | --- | --- | --- |
| E1 | **Quota GitHub Actions** disponible pour un dépôt privé | les minutes ne sont plus gratuites comme en public : vérifier le plan, le quota et le coût | |
| E2 | **CodeQL / code scanning** disponible sur dépôt privé avec le plan retenu | à confirmer avant bascule : sur dépôt privé, l'analyse de code peut relever d'une offre payante | |
| E3 | **GHCR privé** : publication et lecture d'images | vérifier que le déploiement peut encore tirer l'image | |
| E4 | Dependabot et alertes de sécurité toujours actifs | | |
| E5 | Badges du README pointant vers des ressources devenues privées | corriger ou retirer | |

## F. Après la bascule — avant tout tag

| # | Vérification | Attendu | Fait le |
| --- | --- | --- | --- |
| F1 | **Relancer l'intégralité de la CI** sur `main` | tous les jobs bloquants au vert, y compris `License and distribution compliance` | |
| F2 | Vérifier que `deploy` peut authentifier et pousser sur GHCR privé | essai contrôlé, sans tag | |
| F3 | Vérifier que CodeQL a bien produit une analyse | résultats visibles, pas un job vert sans analyse | |
| F4 | Vérifier que les checks requis sont toujours appliqués sur `main` | | |

## G. Rollback

| # | Vérification | Attendu | Fait le |
| --- | --- | --- | --- |
| G1 | Procédure documentée pour repasser en public si un blocage apparaît | opération réversible côté GitHub | |
| G2 | Effets de bord du retour en public identifiés | notamment réexposition immédiate du code | |

---

## Verrou

```
INTERDICTION DE TAGUER
tant que A, B, C, D, E, F ne sont pas intégralement vérifiés et datés.
```

Cette interdiction s'ajoute à celles déjà en vigueur : `tag-guard` refuse un tag
stable tant que `docs/governance/CLINICAL_STATUS` vaut `REAL_DATA_NO_GO`, et la
qualification des composants tiers reste bloquante pour toute distribution
externe (voir [`../../THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) §6).

## Statut

| Statut | Valeur |
| --- | --- |
| `TARGET_REPOSITORY_VISIBILITY` | `PRIVATE_BEFORE_TAG` — décidé |
| Visibilité actuelle | **publique — inchangée** |
| Vérifications effectuées | **aucune ligne cochée à ce jour** |
