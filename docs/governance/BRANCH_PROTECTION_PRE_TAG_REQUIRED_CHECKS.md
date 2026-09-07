# Protection de branche — contrôles requis avant le tag

> **Audit seulement. La règle GitHub n'a pas été modifiée** et ne doit pas l'être
> au titre de cette préparation. Ce document compare l'état constaté à l'état
> cible, et dit ce qui manque.

Relevé le 2026-09-06 sur `main`.

## 1. Le problème

Le pipeline exige neuf jobs avant de publier. La **protection de branche**, elle,
n'en exige que deux avant de fusionner. Autrement dit : la conformité de licence,
les preuves de source Debian, la stack Docker, la restauration de sauvegarde,
CodeQL et les E2E **tournent, mais n'empêchent pas une fusion s'ils échouent**.

Un rouge sur l'un d'eux n'arrête aujourd'hui que la *publication*. Il n'arrête
pas l'arrivée du code sur `main` — d'où il repartira dans la version suivante.

## 2. État constaté

| Réglage | Valeur |
| --- | --- |
| Force push | **interdit** ✅ |
| Suppression de branche | **interdite** ✅ |
| Checks requis | **2** |
| Branches à jour avant fusion (`strict`) | non |
| Appliqué aux administrateurs | **non** |
| Historique linéaire requis | non |
| Résolution des conversations requise | non |
| Signatures requises | non |

Les deux checks actuellement requis :

- `Lint, type-check, security and tests`
- `Migrations + flux clinique E2E (PostgreSQL)`

## 3. État cible avant le tag

| Contrôle | Requis aujourd'hui | Requis avant le tag |
| --- | --- | --- |
| Lint, type-check, security and tests | ✅ | ✅ |
| Migrations + flux clinique E2E (PostgreSQL) | ✅ | ✅ |
| Sauvegarde et restauration PostgreSQL | ❌ | **à ajouter** |
| CodeQL security analysis | ❌ | **à ajouter** |
| E2E navigateur (Playwright) | ❌ | **à ajouter** |
| Stack Docker production — cœur sans Grafana | ❌ | **à ajouter** |
| Preuves de source correspondante (base Debian) | ❌ | **à ajouter** |
| License and distribution compliance | ❌ | **à ajouter** |
| Validate release tag | ❌ | **à ajouter** |
| Image candidate (construite une seule fois) | ❌ | **à ajouter** — les autres en dépendent |

**Sept contrôles manquent**, huit avec l'image candidate.

### Ce qui doit rester hors des gates

`Overlay de supervision optionnel (Grafana)` **ne doit pas** devenir un check
requis. Grafana est une intégration externe et optionnelle : un cœur sain ne
doit pas être bloqué par un composant que RUGGYLAB ne distribue pas. Le job
tourne, il informe, il ne barre pas la route.

## 4. Réglages à examiner en même temps

Ces points ne sont pas dans le mandat, mais les relever maintenant coûte moins
cher que de les découvrir après le tag.

| Réglage | Constat | Remarque |
| --- | --- | --- |
| `enforce_admins` | désactivé | le propriétaire peut fusionner en contournant les checks — acceptable sur un dépôt à un seul mainteneur, à assumer explicitement |
| `strict` (branche à jour) | désactivé | une PR verte sur une base ancienne peut casser `main` après fusion ; les quatre PR de cette série l'ont montré |
| Résolution des conversations | désactivée | sans effet ici : aucune revue n'est ouverte |

## 5. Comment appliquer

Le changement se fait dans les réglages du dépôt (Settings → Branches → règle
sur `main`), ou par API. **Les noms doivent correspondre exactement** au champ
`name:` de chaque job dans `.github/workflows/ci.yml` — un nom approximatif crée
un check requis qui n'arrivera jamais, et bloque définitivement toute fusion.

Après application : ouvrir une PR de test et vérifier que les neuf contrôles
apparaissent bien comme requis, avant de créer quelque tag que ce soit.

## 6. Statut

```
BRANCH_PROTECTION_UPDATE_REQUIRED
```

Tant que ce statut tient, la protection de branche est **plus permissive que le
pipeline de release**. Ce n'est pas bloquant pour continuer à développer ; ça
l'est pour taguer.
