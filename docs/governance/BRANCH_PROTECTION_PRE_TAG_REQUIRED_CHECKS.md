# Protection de branche — contrôles requis avant le tag

> **Audit seulement. La règle GitHub n'a pas été modifiée** et ne doit pas l'être
> au titre de cette préparation. Ce document compare l'état constaté à l'état
> cible, et dit ce qui manque.

Premier relevé le 2026-09-06. **Relevé à nouveau le 2026-09-09** (lot B du gate
G0), par lecture directe de l'API :

```
gh api repos/rommellnelson-ux/ruggylab-os/branches/main/protection
```

## 1. Le problème

Le pipeline exige dix jobs avant de publier. La **protection de branche**, elle,
n'en exige que deux avant de fusionner. Autrement dit : la conformité de licence,
les preuves de source Debian, la stack Docker, la restauration de sauvegarde,
CodeQL, les E2E et **les deux baselines G0** *tournent, mais n'empêchent pas une
fusion s'ils échouent*.

Un rouge sur l'un d'eux n'arrête aujourd'hui que la *publication*. Il n'arrête
pas l'arrivée du code sur `main` — d'où il repartira dans la version suivante.

## 2. État constaté — lecture du 2026-09-09

Valeurs telles que l'API les renvoie. Rien n'est déduit d'une capture d'écran ni
d'un souvenir.

| Réglage (champ d'API) | Valeur lue |
| --- | --- |
| `required_status_checks.contexts` | **2** |
| `required_status_checks.strict` (branche à jour avant fusion) | **`false`** |
| `enforce_admins.enabled` | **`false`** |
| `required_pull_request_reviews` | **absent** — aucune revue exigée |
| `required_signatures.enabled` | `false` |
| `required_linear_history.enabled` | `false` |
| `required_conversation_resolution.enabled` | `false` |
| `allow_force_pushes.enabled` | `false` ✅ |
| `allow_deletions.enabled` | `false` ✅ |
| `block_creations.enabled` | `false` |
| `lock_branch.enabled` | `false` |

Les deux checks actuellement requis, tels qu'ils sont inscrits :

- `Lint, type-check, security and tests`
- `Migrations + flux clinique E2E (PostgreSQL)`

**Rien n'a changé depuis le relevé du 2026-09-06.** Les deux baselines G0
existent désormais dans le pipeline mais ne figurent pas parmi les contrôles
requis.

## 3. État cible avant le tag

Deux familles distinctes, qu'il ne faut pas mélanger : ce qui garde **la
fusion**, et ce qui garde **la publication**.

### 3.1 Contrôles de fusion recommandés

Ceux-ci décrivent la santé du code qui entre sur `main`. Ils sont rapides,
déterministes, et ne dépendent d'aucun état externe mutable.

| Contrôle (`name:` du job) | Requis aujourd'hui | Recommandé |
| --- | :-: | :-: |
| `Lint, type-check, security and tests` | ✅ | ✅ |
| `Migrations + flux clinique E2E (PostgreSQL)` | ✅ | ✅ |
| `CodeQL security analysis` | ❌ | **à ajouter** |
| `G0 — Architecture and data baseline` | ❌ | **à ajouter** |
| `G0 — Security baseline and secret scan` | ❌ | **à ajouter** |

**Trois contrôles manquent** parmi les contrôles de fusion.

### 3.2 Gates de publication — à distinguer

Ceux-ci gardent la *publication*, pas la fusion. Les rendre obligatoires à la
fusion allongerait chaque PR d'une construction d'image complète, sans protéger
`main` davantage : un défaut de licence ou de source Debian n'arrive pas par
surprise dans un commit, il arrive au moment où l'on distribue.

| Contrôle | Rôle |
| --- | --- |
| `Sauvegarde et restauration PostgreSQL` | preuve de restaurabilité |
| `Image candidate (construite une seule fois)` | identité de l'artefact publié |
| `Stack Docker production — cœur sans Grafana` | démarrage de la pile réelle |
| `Preuves de source correspondante (base Debian)` | obligation de source |
| `License and distribution compliance` | conformité des licences |
| `Validate release tag` | garde de tag et de gouvernance |
| `E2E navigateur (Playwright)` | parcours navigateur |

Le pipeline les enchaîne déjà en `needs:` de `deploy` et `release` : ils sont
donc **déjà bloquants pour publier**. Les inscrire en plus comme checks requis à
la fusion est une décision à part, à prendre en connaissance du coût.

### 3.3 Ce qui doit rester hors des gates

`Overlay de supervision optionnel (Grafana)` **ne doit pas** devenir un check
requis. Grafana est une intégration externe et optionnelle : un cœur sain ne
doit pas être bloqué par un composant que RUGGYLAB ne distribue pas. Le job
tourne, il informe, il ne barre pas la route.

## 4. Réglages à examiner en même temps

| Réglage | Constat lu | Remarque |
| --- | --- | --- |
| `enforce_admins` | **`false`** | Le propriétaire peut fusionner en contournant les checks. Acceptable sur un dépôt à un seul mainteneur — **à assumer explicitement**, car cela signifie qu'aucun des contrôles ci-dessus n'est inconditionnel. |
| `strict` | **`false`** | Une PR verte sur une base ancienne peut casser `main` après fusion. Les PR de cette série l'ont montré. Passer à `true` impose de rebaser avant fusion. |
| `required_pull_request_reviews` | **absent** | Aucune revue exigée. Sur un dépôt à un seul mainteneur, l'exiger bloquerait toute fusion ; à revoir si un second mainteneur arrive. |
| Résolution des conversations | `false` | Sans effet aujourd'hui : aucune revue n'est ouverte. |

## 5. Comment appliquer

**Les noms doivent correspondre exactement** au champ `name:` de chaque job dans
`.github/workflows/ci.yml`. Un nom approximatif crée un check requis qui
n'arrivera jamais, et bloque définitivement toute fusion. Attention en
particulier au tiret cadratin de `G0 — …` : c'est un « — » (U+2014), pas un
trait d'union.

Par l'interface : Settings → Branches → règle sur `main`.

Par API — la requête ci-dessous **remplace** l'objet de protection entier ; tout
champ omis est réinitialisé, c'est pourquoi les réglages actuels y sont
reconduits explicitement :

```bash
cat > /tmp/protection.json <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Lint, type-check, security and tests",
      "Migrations + flux clinique E2E (PostgreSQL)",
      "CodeQL security analysis",
      "G0 — Architecture and data baseline",
      "G0 — Security baseline and secret scan"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": false
}
JSON

gh api -X PUT repos/rommellnelson-ux/ruggylab-os/branches/main/protection \
  --input /tmp/protection.json
```

### 5.1 Avant d'appliquer — sauvegarder l'état

Sans cette sauvegarde, le retour arrière serait une reconstitution de mémoire :

```bash
gh api repos/rommellnelson-ux/ruggylab-os/branches/main/protection \
  > protection-avant-$(date -u +%Y%m%dT%H%M%SZ).json
```

### 5.2 Retour arrière

Rejouer le même `PUT` avec l'état sauvegardé, réduit aux champs modifiables :

```bash
gh api -X PUT repos/rommellnelson-ux/ruggylab-os/branches/main/protection \
  --input protection-avant-<horodatage>.json
```

Si la sauvegarde est perdue, l'état du 2026-09-09 est celui du §2 : `strict`
à `false` et les deux seuls contrôles de la liste initiale.

### 5.3 Contrôle après application

```bash
gh api repos/rommellnelson-ux/ruggylab-os/branches/main/protection \
  --jq '{strict: .required_status_checks.strict,
         checks: [.required_status_checks.checks[].context],
         admins: .enforce_admins.enabled}'
```

Attendu : `strict = true`, cinq contextes, `admins = false`. Puis ouvrir une PR
de vérification et **constater que les cinq contrôles apparaissent bien comme
requis** avant de créer quelque tag que ce soit. Un contexte mal orthographié ne
se voit qu'à ce moment-là — et il bloque alors toute fusion.

## 6. Statut

```
BRANCH_PROTECTION_UPDATE_REQUIRED
```

Tant que ce statut tient, la protection de branche est **plus permissive que le
pipeline de release**. Ce n'est pas bloquant pour continuer à développer ; ça
l'est pour taguer.

Ce document **propose**. Il ne modifie rien : le lot B n'a pas touché à la
protection de branche, et ne doit pas y toucher.
