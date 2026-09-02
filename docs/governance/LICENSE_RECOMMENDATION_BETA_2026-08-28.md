# Note de décision — licence de la bêta technique `v0.8.0-beta.1`

> ## ✅ Suite donnée — 2026-08-28
>
> La recommandation ci-dessous **a été suivie**. Le titulaire des droits,
> **WOGNIN Nelson Rommell Boni Ruggairrhye**, a retenu une licence propriétaire
> d'évaluation : **RuggyLab Evaluation License 1.0**.
>
> Voir [`LICENSE_DECISION_BETA_2026-08-28.md`](LICENSE_DECISION_BETA_2026-08-28.md)
> et [`../../LICENSE.md`](../../LICENSE.md).
>
> La note est **conservée telle quelle** : elle documente le raisonnement qui a
> conduit à la décision, et les options écartées restent utiles si la question
> est rouverte pour une version ultérieure.

---

> **PROJET DE DÉCISION — À VALIDER ET SIGNER PAR LE PROPRIÉTAIRE.**
> Cette note **recommande** ; elle ne décide rien. Aucun fichier `LICENSE` n'a
> été ajouté au dépôt. Tant que la décision n'est pas prise et mise en œuvre,
> `LICENSE_DECISION_REQUIRED` reste bloquant pour le tag.

- **Date de rédaction** : 2026-08-28
- **Objet** : licence applicable à la préversion technique
- **Constat de départ** : `docs/governance/LICENSE_DECISION_REQUIRED.md`
- **Décideur** : Nelson Rommell Wognin, propriétaire du code
- **Nature** : recommandation d'ingénierie, **pas un conseil juridique**

---

## 1. Ce qui est constaté

GPL-2.0 est **déclarée** à trois endroits — `pyproject.toml` (classifier OSI),
`Dockerfile` (`org.opencontainers.image.licenses`), `README.md` (badge) — mais
le dépôt **ne contient aucun fichier `LICENSE`**, et l'historique Git ne porte
aucun commit de décision.

Le dépôt est **public**. En l'absence de texte de licence, le droit d'auteur par
défaut s'applique : personne n'a le droit de réutiliser le code. La déclaration
GPL-2.0 crée donc une contradiction entre ce qui est annoncé et ce qui est
juridiquement opposable.

## 2. Recommandation

**Pour la bêta technique : licence propriétaire d'évaluation — tous droits
réservés, usage d'évaluation interne uniquement.**

Trois raisons.

**a) C'est la seule option cohérente avec le statut `REAL_DATA_NO_GO`.** La
version est explicitement destinée à la qualification technique sur données
fictives. Une licence open source autoriserait un tiers à la déployer sur des
données réelles, ce que la gouvernance interdit précisément. Une licence
d'évaluation aligne le droit d'usage sur le statut clinique.

**b) La GPL-2.0 est irréversible en pratique.** Une fois une version distribuée
sous GPL-2.0, les destinataires conservent leurs droits sur cette version, y
compris celui d'exiger le code source et de le redistribuer. On peut relicencier
les versions *futures*, jamais celle déjà publiée. À l'inverse, partir de « tous
droits réservés » laisse **toutes** les options ouvertes : ouvrir plus tard est
toujours possible.

**c) L'exploitation commerciale est un objectif déclaré.** RuggyLab OS est
adossé à une activité de laboratoire privée, avec un objectif de rentabilité.
Sous GPL-2.0, un concurrent pourrait déployer le logiciel et n'aurait aucune
obligation de contribution ni de paiement ; il devrait seulement fournir le code
source à ses propres destinataires. Ce n'est pas nécessairement disqualifiant,
mais c'est une conséquence à accepter en conscience, pas par défaut.

## 3. Ce que cette recommandation n'affirme pas

- Elle **ne dit pas** que l'open source serait un mauvais choix à terme. Pour un
  logiciel de santé destiné au contexte africain, une ouverture ultérieure
  pourrait servir la diffusion, la crédibilité scientifique et l'audit
  indépendant — des objectifs que vous avez exprimés.
- Elle **ne tranche pas** le modèle de licence définitif. Elle porte sur la
  **bêta**, dont la vocation est la qualification interne.
- Elle **n'est pas un avis juridique.** Une licence propriétaire rédigée
  approximativement protège mal. Le texte devrait être relu par un juriste,
  a fortiori pour un logiciel touchant des données de santé.

## 4. Mise en œuvre si cette recommandation est retenue

Quatre déclarations doivent dire la même chose — c'est l'incohérence actuelle
qui pose problème, autant que l'absence de texte :

| Fichier | Action |
| --- | --- |
| `LICENSE` | **à créer** — texte propriétaire d'évaluation (à faire relire) |
| `pyproject.toml` | retirer le classifier OSI GPLv2 ; `license = { file = "LICENSE" }` |
| `Dockerfile` | `org.opencontainers.image.licenses="LicenseRef-Proprietary-Evaluation"` |
| `README.md` | remplacer le badge GPL-2.0 par « Tous droits réservés — évaluation » |

Points que le texte devrait couvrir : périmètre d'usage (évaluation interne,
données fictives), interdiction de redistribution, absence de garantie, absence
de destination clinique, propriété intellectuelle, durée, et loi applicable
(Côte d'Ivoire).

**Un test de cohérence est déjà prêt** dans la PR de préparation de version : il
échouera tant que les quatre déclarations ne concordent pas, ce qui empêche
mécaniquement de retomber dans l'état actuel.

## 5. Si une autre option est préférée

| Option | Conséquence principale |
| --- | --- |
| Confirmer GPL-2.0 | ajouter le texte ; tout destinataire peut exiger le source ; dérivé propriétaire impossible |
| Apache-2.0 / MIT | réutilisation libre sans réciprocité ; Apache ajoute une clause de brevets |
| AGPL-3.0 | copyleft étendu à l'usage en réseau ; contraignant pour un déploiement chez des tiers |
| Retirer toute déclaration | statu quo juridique assumé et écrit, au lieu de subi |

## 6. Signature

Aucune ligne ci-dessous ne doit être pré-remplie.

| Rôle | Nom | Date | Signature |
| --- | --- | --- | --- |
| Propriétaire du code | | | |
| Relecture juridique (recommandée) | | | |

Décision retenue :

- [ ] Licence propriétaire d'évaluation (recommandation de la présente note)
- [ ] GPL-2.0 confirmée
- [ ] Autre licence : ……………………………………
- [ ] Retrait de toute déclaration de licence

---

**Tant que cette note n'est pas signée et mise en œuvre,
`LICENSE_DECISION_REQUIRED` demeure, et `v0.8.0-beta.1` ne doit pas être taggée.
Le statut clinique reste `REAL_DATA_NO_GO`.**
