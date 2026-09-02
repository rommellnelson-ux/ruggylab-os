# Préflight — passage du dépôt en privé

> **Rapport de constat, relevé le 2026-08-28. La visibilité n'a pas été
> modifiée et ne doit pas l'être au titre de la présente préparation.**
>
> Ce document mesure. La liste de ce qu'il faut faire est dans
> [`PRIVATE_REPOSITORY_PRE_TAG_CHECKLIST.md`](PRIVATE_REPOSITORY_PRE_TAG_CHECKLIST.md).

## 1. État actuel du dépôt

| Champ | Valeur relevée |
| --- | --- |
| Dépôt | `rommellnelson-ux/ruggylab-os` |
| Visibilité | **publique** |
| Propriétaire | compte **personnel** (`User`), pas une organisation |
| Branche par défaut | `main` |
| Taille | ~3,8 Mo |
| Archivé | non |

## 2. Forks publics existants

**Zéro fork.** C'est le meilleur cas possible : aucune copie du dépôt ne
subsistera hors de votre contrôle après la bascule.

| Indicateur | Valeur |
| --- | --- |
| Forks | **0** |
| Observateurs (`watchers`) | 0 |
| Étoiles | 0 |

> **Ce que cela ne garantit pas.** Un fork est une copie *déclarée* sur GitHub.
> Un `git clone` ne laisse aucune trace. Zéro fork signifie qu'aucune copie
> *visible* ne persistera — pas qu'aucune copie n'existe. Le dépôt a été public,
> et ce qui a été publié a pu être copié ou indexé. **Le passage en privé
> protège l'avenir, pas le passé.** C'est précisément pourquoi le tag doit venir
> après.

## 3. Collaborateurs et accès

| Compte | Rôle |
| --- | --- |
| `rommellnelson-ux` | `admin` (propriétaire) |

**Un seul compte, celui du propriétaire.** Aucun accès tiers à révoquer, aucun
arbitrage à faire. Restent à recenser manuellement — l'API ne les expose pas
toutes de la même façon : clés de déploiement, jetons d'accès personnel et
applications GitHub installées.

## 4. Règles de branche

Protection active sur `main` :

| Réglage | Valeur |
| --- | --- |
| Force push | **interdit** ✅ |
| Suppression de branche | **interdite** ✅ |
| Checks requis | `Lint, type-check, security and tests` + `Migrations + flux clinique E2E (PostgreSQL)` |
| Appliquée aux administrateurs | **non** |
| Historique linéaire requis | non |
| Résolution des conversations requise | non |
| Signatures requises | non |

> **Écart constaté, indépendant de la visibilité.** Seuls **deux** des jobs
> bloquants sont des *checks requis*. `License and distribution compliance`,
> `Stack Docker production`, `Sauvegarde et restauration PostgreSQL`, `CodeQL` et
> `E2E navigateur` tournent, mais **n'empêchent pas une fusion** s'ils échouent.
> Le pipeline de release, lui, les exige tous — la protection de branche est donc
> plus permissive que le pipeline. À corriger, de préférence **avant** la
> bascule, tant que la configuration est facile à vérifier.

## 5. Intégration continue — quota et coût

C'est le point le plus concret, et le seul qui coûte de l'argent.

| Mesure | Valeur relevée |
| --- | --- |
| Durée cumulée des jobs, dernier run complet | **~15 minutes** (10 jobs) |
| Runs déclenchés en août 2026 | **66** |
| Consommation facturée aujourd'hui | **0** — les dépôts publics sont gratuits |

**Estimation après bascule**, en incluant les jobs ajoutés par les PR en cours
(`license-compliance`, `monitoring-overlay`, `debian-source-evidence`), soit
environ 25 minutes cumulées par run :

| Hypothèse | Minutes / mois |
| --- | --- |
| 66 runs × 15 min (rythme et périmètre actuels) | ~990 |
| 66 runs × 25 min (périmètre après fusion des PR) | **~1 650** |

L'inclusion `GitHub Free` pour un compte personnel est de **2 000 minutes par
mois** sur dépôt privé. L'estimation haute en consomme **plus de 80 %**, sans
marge pour un mois chargé. Deux conséquences à assumer avant de basculer :

- soit prévoir un plan payant ou un budget de dépassement ;
- soit réduire la fréquence ou le périmètre des runs — par exemple en réservant
  les jobs les plus lourds (`docker-stack`, `monitoring-overlay`,
  `debian-source-evidence`) aux PR vers `main` et aux tags, plutôt qu'à chaque
  poussée.

**À vérifier avant la bascule** : le plan réel du compte et le quota associé.
L'API ne les a pas renvoyés avec le jeton utilisé ici.

## 6. Analyse de code (CodeQL)

| Mesure | Valeur |
| --- | --- |
| Analyse active | oui |
| Alertes ouvertes | **6**, toutes hautes, analysées et justifiées |

> **Point de vigilance sérieux, à confirmer avant la bascule.** L'analyse de code
> est gratuite sur les dépôts **publics**. Sur un dépôt **privé**, sa
> disponibilité dépend du plan : elle relève d'une offre payante hors des
> formules gratuites pour compte personnel.
>
> Si l'analyse cesse de fonctionner, le job `codeql` échouera ou ne produira plus
> de résultat, et il est une dépendance bloquante de `deploy`. **Le tag serait
> alors impossible, ou pire, produit par un pipeline dont un gate ne prouve plus
> rien.**
>
> À vérifier concrètement, pas à supposer : basculer, relancer la CI, et
> **contrôler que CodeQL a bien produit une analyse** — un job vert sans analyse
> n'est pas une analyse.

## 7. Registre d'images (GHCR)

Le job `deploy` publie sur `ghcr.io/rommellnelson-ux/ruggylab-os`. Après
bascule, les paquets associés à un dépôt privé héritent normalement de sa
visibilité.

**Non vérifié ici** : le jeton utilisé n'a pas la portée `read:packages`. À
contrôler après bascule : que `deploy` peut toujours s'authentifier et pousser,
et que le déploiement peut toujours **tirer** l'image — un `docker pull` depuis
un registre devenu privé exige une authentification qui n'était pas nécessaire
avant.

## 8. Secrets

Aucun secret n'a été trouvé par les analyses en place, et `.env` n'est pas suivi.
Deux points à traiter avant la bascule :

- l'analyse doit porter sur l'**historique complet**, pas sur `HEAD` ;
- si un secret a été exposé pendant la période publique, il doit être
  **révoqué**. Passer en privé ne le neutralise pas : il le cache.

## 9. Rollback

Repasser en public est possible côté GitHub, et immédiat. Deux effets à avoir en
tête :

- le code redevient **immédiatement** accessible ;
- les paquets GHCR ne changent pas forcément de visibilité en même temps que le
  dépôt : à revérifier explicitement dans les deux sens.

Le retour arrière étant simple, le risque principal n'est pas la bascule
elle-même mais **un tag créé pendant que la CI est cassée**. D'où le verrou.

## 10. Ce qui resterait accessible après la bascule

| Élément | Après passage en privé |
| --- | --- |
| Code du dépôt | privé |
| Forks existants | **aucun** — rien à hériter |
| Clones locaux hors GitHub | inchangés, hors de tout contrôle |
| Contenu déjà indexé ou mis en cache par des tiers | inchangé, irréversible |
| Releases publiées (`v0.7.4` et antérieures) | deviennent privées avec le dépôt |
| Images déjà poussées sur GHCR | à vérifier explicitement (§7) |

## 11. Synthèse

```
PRIVATE_REPOSITORY_PREFLIGHT_READY
```

Le préflight est **prêt** : les mesures sont faites, les risques identifiés et
chiffrés. Trois d'entre eux appellent une décision **avant** la bascule, et
aucun n'est technique :

1. **Quota Actions** — l'estimation haute consomme plus de 80 % de l'inclusion
   gratuite. Plan payant, ou réduction du périmètre des runs.
2. **CodeQL sur dépôt privé** — à confirmer ; c'est un gate bloquant de
   `deploy`.
3. **Checks requis incomplets** sur `main` — écart préexistant, à corriger tant
   que c'est facile.

**La visibilité n'a pas été modifiée.** Aucun tag ne doit être créé avant que la
liste de vérification soit intégralement cochée et datée.
