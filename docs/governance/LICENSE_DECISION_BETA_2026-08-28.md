# Décision de licence — bêta technique `v0.8.0-beta.1`

> **PROJET DE DÉCISION — À VALIDER ET SIGNER.** Aucune signature n'est
> pré-remplie ni simulée. Le document enregistre une décision de principe prise
> par le titulaire des droits ; sa mise en œuvre technique est faite, sa
> validation juridique ne l'est pas.

- **Date de rédaction** : 2026-08-28
- **Portée** : version `v0.8.0-beta.1` de RUGGYLAB OS
- **Fait suite à** : [`LICENSE_DECISION_REQUIRED.md`](LICENSE_DECISION_REQUIRED.md)
  et [`LICENSE_RECOMMENDATION_BETA_2026-08-28.md`](LICENSE_RECOMMENDATION_BETA_2026-08-28.md)

---

## 1. Décision

RUGGYLAB OS `v0.8.0-beta.1` est publié sous **RuggyLab Evaluation License 1.0**,
licence **propriétaire d'évaluation**, identifiant
`LicenseRef-RuggyLab-Evaluation-1.0`.

Le texte figure à la racine du dépôt : [`LICENSE.md`](../../LICENSE.md).

## 2. Titularité des droits

**Titulaire actuel des droits patrimoniaux :**
**WOGNIN Nelson Rommell Boni Ruggairrhye.**

Éléments de fait retenus :

| Fait | Portée |
| --- | --- |
| Développement mené à titre **personnel et indépendant** | pas d'œuvre de commande |
| **Aucune commande** ni mission officielle à l'origine du logiciel | pas de dévolution contractuelle |
| **Aucun financement institutionnel** créateur de droits | pas de copropriété par financement |
| **Aucune instruction hiérarchique** portant sur sa réalisation | pas de création dans l'exercice de fonctions |
| **Aucune clause d'attribution** à une institution | pas de transfert stipulé |
| **Aucun autre contributeur humain** titulaire de droits identifié | titularité unique |

## 3. Site d'évaluation

Le **Centre de Santé des Armées de la Garde Républicaine du Plateau** est un
**site d'évaluation** et un futur utilisateur/licencié potentiel.

Il ne détient **aucun droit de propriété** sur la technologie. La mise à
disposition de locaux, de matériel ou d'utilisateurs pour les essais ne crée
aucun droit sur le logiciel — point rappelé au §9 de la licence.

## 4. Transfert futur envisagé

Une société **RUGGYLAB** est en cours de constitution. Elle est le bénéficiaire
**envisagé** d'un transfert ultérieur des droits, par **acte écrit** de cession
ou d'apport.

Tant que cet acte n'est pas intervenu, la titularité reste celle énoncée au §2.
Aucun transfert n'est réputé acquis du seul fait de la présente décision.

## 4 bis. Décisions de distribution — 2026-08-28

Prises par le titulaire, elles ne sont plus des options ouvertes.

| Décision | Valeur | Où elle s'applique |
| --- | --- | --- |
| `EVALUATION_DURATION` | **6 mois** | [`../../LICENSE.md`](../../LICENSE.md) §4.1 |
| `RENEWAL` | **autorisation écrite uniquement** | `LICENSE.md` §4.1 |
| `TARGET_REPOSITORY_VISIBILITY` | **privé avant tag** | [`PRIVATE_REPOSITORY_PRE_TAG_CHECKLIST.md`](PRIVATE_REPOSITORY_PRE_TAG_CHECKLIST.md) |
| `REDIS_7_4_DISTRIBUTION` | **écarté** | `THIRD_PARTY_NOTICES.md` §6.1 |
| `REDIS_REPLACEMENT` | **Valkey** | PR technique distincte |
| `GRAFANA_CORE_DEPENDENCY` | **non** | `THIRD_PARTY_NOTICES.md` §6.2 |
| `GRAFANA_DISTRIBUTED_BY_RUGGYLAB` | **non** | idem |
| `GRAFANA_OPTIONAL_EXTERNAL_SERVICE` | **oui** | PR technique distincte |
| `PROMETHEUS_RETAINED` | **oui** | stack principale |

**Une décision n'est pas une mise en œuvre.** Les statuts
`REDIS_REPLACED_BY_VALKEY` et `GRAFANA_EXTERNALIZED` ne seront prononcés
qu'après fusion des PR techniques correspondantes et requalification des
notices. D'ici là, les marqueurs de revue obligatoire restent en place : ils
décrivent l'état du dépôt, pas l'intention du titulaire.

**Durée et cessation.** L'autorisation d'évaluation vaut six mois au maximum à
compter de l'autorisation écrite, sans reconduction tacite. Elle cesse par
anticipation en cas de remplacement de version, de retrait pour raison de
sécurité, de violation des conditions d'évaluation, de décision du titulaire ou
de modification du statut de gouvernance. Le modèle d'autorisation, **non
signé**, est disponible :
[`EVALUATION_AUTHORIZATION_CSA_GR_PLATEAU_TEMPLATE.md`](EVALUATION_AUTHORIZATION_CSA_GR_PLATEAU_TEMPLATE.md).

## 5. Ce que cette décision ne tranche pas

- **La licence des versions futures.** La présente décision porte sur
  `v0.8.0-beta.1`. Une ouverture ultérieure — pour la diffusion, la crédibilité
  scientifique ou l'audit indépendant — reste possible et n'est pas écartée.
- **Le texte contractuel destiné à un tiers externe.** Les clauses du §12 de la
  licence (droit applicable, juridiction, durée, limitation de responsabilité,
  règlement des litiges) **exigent une validation juridique**.
- **La conformité des composants tiers.** Elle fait l'objet d'une qualification
  distincte, consignée dans [`../../THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).
  Certains composants restent en revue obligatoire.

## 6. Statuts maintenus

| Statut | Valeur | Effet |
| --- | --- | --- |
| `REAL_DATA_NO_GO` | **maintenu** | aucune utilisation clinique réelle, aucune donnée patient |
| `CSA_SYNC_ENABLED` | **`false`** | synchronisation CSA inactive par défaut |
| Interfaces automates | **désactivées** | aucun port automate publié par la stack de base |

La présente décision est une décision de **licence**. Elle n'emporte **aucune**
levée du NO-GO clinique ni aucune autorisation de déploiement.

## 7. Signature

Aucun champ ci-dessous ne doit être pré-rempli.

```
Nom du décideur :
Date :
Signature :
```

---

**Cette décision est réputée non prise tant que le champ signature demeure
vierge.**
