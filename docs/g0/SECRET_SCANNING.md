# G0 — Recherche de secrets : arbre courant, historique, et preuve que ça marche

> **INTERNAL — SECURITY ARCHITECTURE**
> **BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT**
>
> Ce document décrit une architecture de référence, pas une installation. Il ne
> contient aucune adresse IP réelle de site, aucun identifiant, aucun secret,
> aucun nom de compte, aucune topologie VLAN réelle et aucune donnée patient —
> et il ne doit pas en recevoir tant que le dépôt reste public.
>
> Ce bandeau est une **mention de classification, pas un contrôle d'accès** : il
> n'empêche personne de lire ce fichier. Le seul contrôle réel serait la
> visibilité du dépôt.

> **Aucune valeur n'est reproduite ici, pas même tronquée.** Un fragment de
> secret reste un indice. Ne circulent que l'emplacement, la règle déclenchée,
> l'empreinte et le jugement porté.
>
> Barrière : [`scripts/g0_secret_gate.py`](../../scripts/g0_secret_gate.py).
> Registre d'exceptions :
> [`docs/governance/SECRET_SCAN_EXCEPTIONS.json`](../governance/SECRET_SCAN_EXCEPTIONS.json).
> Revue de la baseline :
> [`artifacts/g0/secret-scan-summary.json`](../../artifacts/g0/secret-scan-summary.json).

## 1. L'état de départ : un contrôle décoratif

Avant le lot B, `.github/workflows/ci.yml` portait :

```yaml
- name: Secret scan (advisory)
  continue-on-error: true
  run: python -m detect_secrets.pre_commit_hook --baseline .secrets.baseline $(git ls-files)
```

Trois défauts, tous mesurés, aucun corrigé par ce lot :

1. **`continue-on-error: true`.** Le scan ne bloquait rien.
2. **Il échouait déjà.** Exécuté tel quel sur l'arbre courant, il sort en code 1
   et relève des détections dans **88 fichiers**, alors que `.secrets.baseline`
   n'en couvre que **14**. Personne n'en était averti, puisque l'échec était
   avalé.
3. **Les chemins de `.secrets.baseline` sont écrits à la mode Windows.** Treize
   de ses quatorze clés portent des séparateurs `\`. Sur un runner Linux,
   `detect-secrets` produit `tests/conftest.py` et ne retrouve jamais
   `tests\conftest.py` : **aucune** entrée de la baseline ne s'applique en CI.
   Le fichier versionné n'est pas réécrit ici — le lot B qualifie, le lot D
   remédie. La barrière normalise les séparateurs **à la lecture**, et cette
   compensation est elle-même la preuve du défaut.

Constats **B-10** et **B-11**. Voir [`SECURITY_FINDINGS.md`](SECURITY_FINDINGS.md).

## 2. Ce que la barrière fait maintenant

| Étape | Outil | Portée | Bloquant |
| --- | --- | --- | --- |
| Job `Lint, type-check, security and tests` | `detect-secrets` 1.5.0 via la barrière | arbre courant, fichiers suivis par Git | **oui** |
| Job `G0 — Security baseline and secret scan` | `detect-secrets` + **Gitleaks 8.30.1** | arbre courant **et historique Git complet** | **oui** |
| Sondes de non-vacuité | les deux outils | dépôt jetable hors du dépôt principal | **oui** |

Le job de sécurité fait un `checkout` avec **`fetch-depth: 0`** et refuse de
continuer si le dépôt est superficiel : un scan d'historique sur un clone d'un
seul commit rendrait un vert sans signification.

### Épinglage de l'outil d'historique

`GITLEAKS_VERSION: "8.30.1"` — version **exacte**, jamais `latest`. Une version
flottante changerait le jeu de règles sans qu'aucun commit ne l'indique, et le
résultat d'hier ne serait plus reproductible.

`GITLEAKS_SHA256` est inscrit **en dur** dans le workflow et vérifié par
`sha256sum --check --strict` avant toute extraction. Un tag de release GitHub
est mutable : se contenter du fichier de checksums publié dans la même release
ne prouverait rien, puisqu'un attaquant capable de remplacer l'archive
remplacerait aussi ce fichier. La valeur est ancrée par **trois canaux
concordants**, relevés le 2026-09-09 :

1. `sha256sum` calculé localement sur les **8 230 402 octets** réellement
   téléchargés de `gitleaks_8.30.1_linux_x64.tar.gz` ;
2. le champ `digest` renvoyé par l'API des releases GitHub ;
3. `gitleaks_8.30.1_checksums.txt` publié dans la release.

Toute montée de version doit refaire les trois. C'est la même méthode que celle
déjà employée pour `actionlint` dans le job `test`.

### Ce que la CI ne montre jamais

Aucune valeur détectée n'est affichée. Gitleaks est appelé avec `--redact=100`,
et la barrière ne recopie de son rapport que le chemin, la règle et le commit.
Les **rapports bruts de Gitleaks ne sont pas publiés** en artefact : ils portent
l'auteur, l'adresse de courriel et le message de chaque commit concerné, qui
n'ont rien à faire dans un fichier téléchargeable. Seul le rapport expurgé de la
barrière l'est.

## 3. Audit de `.secrets.baseline`

Revue emplacement par emplacement, sans reproduire aucune valeur.

| | |
| --- | --- |
| Version du format | `1.5.0` |
| Fichiers couverts | **14** |
| Entrées | **30** |
| Entrées non revues | **0** |
| **Secrets réels** | **0** |
| Rotation nécessaire | **0** |
| Chemins à séparateurs Windows | **13** |

Nature des 30 entrées :

| Caractère | Entrées | Ce que sont ces valeurs |
| --- | ---: | --- |
| `FACTICE_DE_TEST` | **19** | Identifiants de comptes créés puis détruits par le test lui-même, sur une base jetable. Plusieurs tests portent précisément sur le refus des mots de passe faibles : les écrire est la condition du test. |
| `EXEMPLE_DOCUMENTAIRE` | **7** | Marque-place de `.env.example` et valeurs d'illustration de `docs/SECRETS_MANAGEMENT.md`, destinés à être remplacés au déploiement. |
| `SECRET_DE_CI_NON_PRODUCTION` | **4** | Identifiants de bases jetables créées et détruites dans le runner, écrits en clair pour que le pipeline soit rejouable. |

**Aucune valeur ne demande de rotation** : aucune ne désigne un système durable.
Ce jugement porte sur les 30 entrées de la baseline, pas sur l'historique.

## 4. Le registre d'exceptions

`.secrets.baseline` ne couvre pas l'arbre d'aujourd'hui. Plutôt que de le
réécrire — ce qui serait une remédiation, donc hors du mandat du lot B — les
détections qu'il ne couvre pas sont inscrites dans un registre séparé, sur le
modèle déjà employé dans le dépôt par `DEBIAN_NOTICE_EXCEPTIONS.json` et
`SBOM_LICENSE_EXCEPTIONS.json`.

Chaque exception porte **quatre champs obligatoires** : l'empreinte
(`fingerprint`, le SHA-1 que `detect-secrets` calcule sur la valeur, ou le
commit pour une détection d'historique), le **chemin**, le **commit** de revue
ou d'introduction, et la **justification**.

**Le registre ne se remplit pas tout seul.** La justification vient d'une
**famille de chemins écrite à la main** dans `scripts/g0_secret_gate.py`. Un
chemin qui n'appartient à aucune famille revue sort en `NON_REVU`, et la
barrière le **refuse** : c'est là qu'un humain doit trancher. Accepter
automatiquement tout ce qui est trouvé aurait produit un registre qui dit oui à
tout — c'est-à-dire pas de barrière.

Familles revues :

| Famille | Chemins | Caractère |
| --- | --- | --- |
| `tests` | `tests/**` | `FACTICE_DE_TEST` |
| `scripts_utilitaires` | `scripts/check_pw.py`, `scripts/verify_db_password.py`, `scripts/uat_smoke.py` | `FACTICE_DE_TEST` |
| `empreintes_publiques` | `artifacts/g0/*.json`, `scripts/g0_provenance.py`, `scripts/g0_secret_gate.py` | `EMPREINTE_PUBLIQUE` |
| `generateurs_g0` | `scripts/g0_*.py` | `LIBELLE_DE_CLASSIFICATION` |
| `documentation` | `.env.example`, `docs/**/*.md`, `docs/**/*.json` | `EXEMPLE_DOCUMENTAIRE` |
| `ci_jetable` | `.github/workflows/*.yml` | `SECRET_DE_CI_NON_PRODUCTION` |

`EMPREINTE_PUBLIQUE` désigne des SHA-256 d'arbres d'entrée et des SHA de commits
Git : une empreinte est publiée pour être comparée, elle n'ouvre aucun accès.
`LIBELLE_DE_CLASSIFICATION` désigne des noms de catégories comme
`AUTHENTIFICATION_SECRET`, dont la valeur est un niveau de risque : le détecteur
de mots-clés relève l'affectation, pas une valeur.

Sont exclus du scan, pour les **deux** scanners : `.secrets.baseline`, le
registre lui-même, les produits d'exécution (`__pycache__`, caches d'outils) et
les fichiers binaires. Ils ne contiennent que des empreintes ; les scanner ferait relever ces
empreintes comme chaînes hexadécimales à forte entropie, qu'il faudrait inscrire
à leur tour dans le registre, dont les nouvelles empreintes seraient relevées à
la génération suivante. `detect-secrets` applique la même exclusion à sa propre
baseline.

**Conséquence à connaître.** Les fichiers de provenance de `artifacts/g0/`
portent des empreintes SHA-256 que le détecteur d'entropie relève. Ils **restent
scannés** : les exclure au motif qu'ils « ne contiennent que des empreintes »
serait une hypothèse sur le comportement futur d'un générateur. En contrepartie,
régénérer une provenance change une empreinte et oblige donc à régénérer le
registre — sans quoi la barrière refuse. C'est la même discipline que celle déjà
imposée par les baselines G0 : régénérer, puis relire le diff.

## 5. Sondes de non-vacuité — la preuve que le scanner voit encore

Un scanner cassé et un dépôt propre produisent exactement le même vert. Sans
sonde, un vert ne prouve rien.

Deux sondes, exécutées **dans un répertoire temporaire hors du dépôt** :

- **Sonde positive** — un fichier porteur d'une sentinelle ayant la forme d'une
  clé d'accès **doit** être détecté. Verdict enregistré :
  `POSITIVE_PROBE_DETECTED`.
- **Sonde négative** — un fichier de texte ordinaire ne **doit pas** l'être.
  Verdict enregistré : `NEGATIVE_PROBE_ACCEPTED`.

Un verdict manquant ou inversé (`POSITIVE_PROBE_MISSED`,
`NEGATIVE_PROBE_FALSE_POSITIVE`) fait échouer le job.

Pour Gitleaks, le dépôt jetable est un **vrai dépôt Git** : la sentinelle est
ajoutée dans un premier commit, **puis retirée** dans un second. L'arbre final
ne la contient plus. La sonde positive ne peut donc réussir que si l'historique
est réellement parcouru — c'est aussi le contrôle du `fetch-depth: 0`.

**Deux formes plutôt qu'une.** Une clé d'accès et un en-tête de clé privée PEM.
Une sonde à forme unique ne teste que la règle qui la reconnaît ; la première
version l'a montré à ses dépens (§6.3).

**La sentinelle n'est écrite en clair nulle part dans le dépôt.** Elle est
assemblée à l'exécution, morceau par morceau, par `scripts/g0_secret_gate.py`.
L'écrire en un seul littéral ferait entrer dans le dépôt principal une valeur
ayant la forme d'un secret actif — exactement ce que cette campagne s'interdit —
et le fichier serait détecté par sa propre barrière. Un test vérifie que la
valeur assemblée n'apparaît ni dans le script ni dans le test lui-même.

## 6. Résultats mesurés

### 6.1 Arbre courant — `detect-secrets`

Mesure du 2026-09-09, sur l'arbre de travail complet du lot B.

| | |
| --- | --- |
| Fichiers scannés | **613** |
| Détections | **229** |
| — couvertes par `.secrets.baseline` | **68** |
| — couvertes par le registre d'exceptions | **161** (127 entrées après déduplication) |
| — **sans couverture écrite** | **0** |

Par règle : `Secret Keyword` 197, `Basic Auth Credentials` 22,
`Hex High Entropy String` 10.

Le registre compte **127 entrées** — une par décision à prendre, et non une
par occurrence : dix lignes portant la même valeur dans le même fichier ne
posent qu'une question. Par famille : `tests` 100, `ci_jetable` 11,
`empreintes_publiques` 7, `documentation` 7, `generateurs_g0` 1,
`scripts_utilitaires` 1. Par scanner : `detect-secrets` 122,
`gitleaks-historique` 3, `gitleaks-arbre` 2.

**Aucun secret réel n'a été trouvé dans l'arbre courant.** Ce jugement est celui
porté famille par famille ci-dessus ; il n'est pas une propriété démontrée du
dépôt, mais la conclusion d'une revue dont chaque entrée est traçable.

### 6.1.1 Une première mesure était fausse — et c'est la CI qui l'a montré

La première version de ce document annonçait **170 détections dans 77
fichiers**. Ces chiffres étaient **faux**, et ils l'étaient d'une manière qui ne
se voyait pas depuis le poste où ils avaient été produits.

`detect-secrets` ouvre les fichiers avec `open(chemin)`, donc avec l'encodage de
la locale. Sous Linux, c'est UTF-8. Sous Windows, c'est `cp1252` — et un fichier
UTF-8 contenant un octet invalide dans cette table y provoque une
`UnicodeDecodeError` que l'outil **avale silencieusement** : le fichier n'est pas
scanné, et rien ne le signale. La mesure locale sous-comptait donc, sans
avertissement.

Le symptôme est mesurable : `tests/test_qc.py` porte une affectation de mot de
passe littérale que la CI Linux relève et que la même commande, sur le même
fichier, ne relevait pas sous Windows. Le premier passage de CI a échoué sur
exactement ce point, en listant 30 détections que le registre ne couvrait pas.

La barrière force désormais la lecture en UTF-8 pendant le scan. Après
correction : **229 détections dans 88 fichiers**, chiffres identiques sous
Windows et sous Linux. C'est la même famille de défaut que l'ordre de tri des
chemins qui avait fait échouer le lot A : *une mesure qui dépend de la machine
qui la produit n'est pas une mesure*.

### 6.2 Historique Git complet — Gitleaks

Le scan d'historique est exécuté par le job
`G0 — Security baseline and secret scan`, sur le dépôt entier
(`gitleaks git . --log-opts="--all"`), après vérification que le clone n'est pas
superficiel.

**Réconciliation du nombre de commits.** Le rapport précédent avançait deux
nombres — 445 accessibles, 367 parcourus — sans relier l'un à l'autre. Un écart
de 78 commits inexpliqué n'est pas une preuve de couverture : c'est une question
ouverte. La barrière mesure désormais la partition et échoue si l'addition ne
tombe pas juste.

| Compteur | Source |
| --- | --- |
| `reachable_commits` | `git rev-list --all` |
| `merge_commits` | `git rev-list --all --merges` |
| `non_merge_commits` | `git rev-list --all --no-merges` |
| `gitleaks_expected_commits_scanned` | = `non_merge_commits` — Gitleaks ne parcourt pas les commits de fusion, qui n'introduisent aucun contenu propre |
| `distinct_commits_present_in_findings` | commits distincts cités par le rapport |
| `is_shallow_repository` | `git rev-parse --is-shallow-repository` |

L'écart s'explique donc par les **commits de fusion**. Si
`reachable = merges + non_merges` ne se vérifie pas, ou si le clone est
superficiel, la barrière émet `HISTORY_SCAN_COUNT_UNRECONCILED` et passe au
rouge — et le statut `G0_SECRET_HISTORY_SCAN_VERIFIED` n'est pas prononcé.
Les valeurs de l'exécution sont dans `secret-gate-report.json`, champ
`history_reconciliation`.

| Portée | Détections brutes | Après application du périmètre commun | Sans couverture écrite |
| --- | ---: | ---: | ---: |
| `detect-secrets`, arbre courant (613 fichiers) | 229 | 229 | **0** |
| Gitleaks, arbre courant | 30 | **2** | **0** |
| Gitleaks, historique complet (367 commits) | 157 | **5** | **0** |
| **Total confronté au registre** | | **236** | **0** |

Les 30 et 157 détections brutes de Gitleaks portaient presque toutes sur
`.secrets.baseline` — Gitleaks relève ses empreintes SHA-1 comme des clés
génériques — et sur un fichier `.pyc` de `__pycache__`. Ces deux-là sont
**hors périmètre** pour les deux scanners.

Le premier passage complet mesurait **416 détections dont 187 sans couverture
écrite**, sur **quatre chemins distincts** :

| Chemin | Portée | Occurrences | Jugement |
| --- | --- | ---: | --- |
| `.secrets.baseline` | arbre + historique | 179 | **Exclu du scan** : le fichier ne contient que des empreintes SHA-1, que Gitleaks relève comme clés génériques. Même raison que pour le registre. |
| `tests/__pycache__/*.pyc` | arbre | 1 | **Exclu du scan** : produit d'exécution, jamais un fichier d'auteur. |
| `.env.example` | historique | 3 | Marque-place documentaires (famille `documentation`). |
| `docs/g0/INVENTORY.md` | arbre + historique | 2 | Identifiants d'un conteneur jetable cités dans une procédure reproductible du lot A. |
| `tests/test_g0_security_baseline.py` | arbre + historique | 2 | Mot de passe littéral du fichier piège de la sonde UTF-8 (famille `tests`). |

Les deux premiers ont été **exclus du périmètre** — `detect-secrets` recevait
déjà une liste filtrée, Gitleaks parcourait tout ; les deux outils ne parlaient
donc pas du même périmètre. Les trois derniers sont **inscrits au registre**.
Il ne reste ensuite aucune détection non couverte.

**Clé d'acceptation pour Gitleaks — corrigée après revue indépendante.**

La première version de cette barrière utilisait **(scanner, chemin, règle)**,
en écartant délibérément l'identité de la détection. L'argument écrit ici était
qu'inclure le SHA du commit rendrait le registre faux à chaque nouveau commit.
L'argument partait d'une prémisse fausse — **le commit n'est pas l'identité
d'une détection** — et sa conséquence était grave.

La revue l'a démontrée par mutation : dans un fichier déjà qualifié, sous une
règle déjà qualifiée, **une seconde valeur détectable passait sans être relue**.
C'est exactement le chemin par lequel un vrai secret serait entré.

La clé est désormais le champ **`Fingerprint`** que Gitleaks compose lui-même :

```
<commit>:<fichier>:<règle>:<ligne>      pour un scan d'historique
<fichier>:<règle>:<ligne>               pour un scan d'arbre
```

Le chemin, la règle, le commit et la ligne restent inscrits comme métadonnées
de lecture. **Aucun ne remplace l'empreinte.** Un finding sans `Fingerprint`
n'est pas accepté par défaut : il produit `GITLEAKS_FINDING_WITHOUT_FINGERPRINT`
et la barrière passe au rouge — on ne laisse pas entrer une détection qu'on ne
sait pas nommer.

Conséquence assumée, et cette fois dans le bon sens : le registre s'allonge. Une
valeur déplacée d'une ligne, une valeur ajoutée dans un fichier déjà revu, une
nouvelle règle sur un chemin connu — **chacune redemande une décision humaine**.
C'est le prix d'un registre qui dit la vérité, et il est plus faible que celui
d'un registre qui rassure.

Les cinq entrées Gitleaks du registre précédent portaient l'ancienne forme
d'empreinte — trois un SHA de commit, deux la chaîne littérale `arbre-courant`.
Elles ont été **retirées** : leur identité n'était pas vérifiable. Elles sont
re-dérivées d'une mesure réelle en CI, puis relues et réinscrites avec leur
`Fingerprint` exact.

### 6.3 Verdict des sondes

Verdicts relevés dans le job, sur la tête de la PR :

| Scanner | Sonde positive | Sonde négative |
| --- | --- | --- |
| `detect-secrets` | `POSITIVE_PROBE_DETECTED` — règles `AWS Access Key` et `Private Key` | `NEGATIVE_PROBE_ACCEPTED` |
| Gitleaks | `POSITIVE_PROBE_DETECTED` — « 2 commits scanned », « leaks found: 2 » | `NEGATIVE_PROBE_ACCEPTED` — « no leaks found » |

Les deux formes de la sentinelle sont donc relevées par les deux outils, et le
fichier propre par aucun.

**La sonde Gitleaks a d'abord échoué — et c'est précisément à cela qu'elle
sert.** Au premier passage, elle est sortie en `POSITIVE_PROBE_MISSED` : les
deux commits du dépôt jetable ont bien été parcourus (« 2 commits scanned »),
mais aucune fuite n'a été relevée. La sentinelle valait alors
`AKIA` + `G0PROBE` + `SENTINEL7` ; les mots `PROBE` et `SENTINEL` la faisaient
écarter par la liste de mots vides de Gitleaks. Le scanner fonctionnait, la
sonde était mal choisie.

Deux passages de CI ont été nécessaires pour la corriger, et chacun a mesuré,
pas supposé. D'abord la valeur, débarrassée de tout mot du dictionnaire. Puis le
**bloc PEM complet** : la deuxième rédaction ne portait que la ligne `BEGIN`,
alors que la règle `private-key` de Gitleaks exige le bloc entier, ligne `END`
comprise — la sonde est ressortie en `POSITIVE_PROBE_MISSED` une seconde fois.
Le corps du bloc n'est pas une clé : c'est l'encodage base64 d'une phrase
française qui le dit.

Une sonde à forme unique ne teste que la règle qui la reconnaît, et sa
disparition se lit alors comme un dépôt propre. Le job affiche désormais les
deux rapports de sonde — ils sont expurgés et le dépôt jetable ne porte que des
valeurs synthétiques — pour qu'un échec soit diagnosticable en une exécution.

## 7. Ce que cette barrière ne prouve pas

- **Un scan propre ne prouve pas l'absence de secret.** Il prouve qu'aucune
  règle des deux jeux employés n'a déclenché. Un secret qui ne ressemble à
  aucune forme connue — une phrase de passe en français, une clé sans préfixe
  reconnaissable — passerait.
- **La revue par famille est un jugement, pas une démonstration.** Elle affirme
  que les valeurs trouvées dans `tests/**` sont des identifiants de test. Un
  vrai secret collé par erreur dans un fichier de test serait accepté par sa
  famille. C'est le prix d'un registre gérable ; c'est aussi sa limite, et elle
  est écrite ici plutôt que découverte plus tard.
- **La barrière ne couvre pas les secrets qui n'ont jamais été commités** :
  variables d'environnement du runner, secrets GitHub Actions, contenu d'un
  `.env` local non suivi.
- **Rien n'est corrigé.** Ni `.secrets.baseline`, ni un secret trouvé dans
  l'historique. La remédiation — réécriture d'historique, rotation — appartient
  au **lot D**, et exigerait une décision explicite du titulaire.

## 8. Rejouer la mesure

```
python scripts/g0_secret_gate.py --tree --probes
python scripts/g0_secret_gate.py --tree --propose /tmp/proposition.json
python -m pytest -q tests/test_g0_security_baseline.py
```

Le scan d'historique demande Gitleaks ; il est exécuté par la CI, qui l'installe
en vérifiant l'empreinte de l'archive.

## 9. Ce que la revue indépendante a corrigé

Quatre défauts d'outillage, dont deux privaient la barrière de son effet.

| # | Défaut | Ce qu'il permettait | Correction |
| --- | --- | --- | --- |
| 1 | Clé d'acceptation Gitleaks réduite à `chemin + règle` | **Une nouvelle valeur détectable, dans un fichier déjà qualifié sous la même règle, passait sans être relue** | Clé = `Fingerprint` exact ; un finding sans empreinte fait échouer la barrière |
| 2 | `except (OSError, UnicodeDecodeError): continue` dans le scan de l'arbre | **Un fichier illisible produisait le même résultat qu'un fichier propre** : zéro détection, barrière verte | Chaque fichier est `SCANNED` ou `EXPLICITLY_EXCLUDED` ; tout autre cas donne `SECRET_SCAN_INCOMPLETE` |
| 3 | Les deux fichiers exclus des règles d'entropie n'étaient relus par personne | Une zone franche du dépôt, versionnée, où écrire n'importe quoi | Validateur spécialisé : schéma exact, champs autorisés, types, empreintes, décisions, et refus de toute valeur détectable |
| 4 | 445 et 367 commits annoncés sans lien entre eux | Une couverture d'historique affirmée, non démontrée | Partition mesurée ; `HISTORY_SCAN_COUNT_UNRECONCILED` si l'addition ne tombe pas juste |

### Une cinquième correction, trouvée par la CI

Le premier passage de l'amendement a échoué, et sur un défaut que la relecture
n'avait pas vu : **six entrées du registre visaient des empreintes qui changent
à chaque régénération**.

`artifacts/g0/*provenance*.json` porte `relevant_input_tree_sha256`, l'empreinte
SHA-256 des fichiers d'entrée. `detect-secrets` la relève comme une chaîne
hexadécimale à forte entropie — ce qu'elle est, sans être un secret. Or la clé
d'acceptation est le hachage de la **valeur** : dès qu'un fichier d'entrée
change, l'empreinte change, l'identité change, et l'entrée du registre devient
caduque.

Il aurait donc fallu réécrire six entrées à chaque régénération. Un registre
qu'on réécrit machinalement est un registre qu'on ne relit plus — précisément
le défaut que cette barrière combat par ailleurs. C'était un piège de
maintenance latent, hérité de la première version.

Ces trois fichiers rejoignent donc l'exclusion structurelle, **pour la même
raison que la baseline et le registre**, et avec la même compensation : ils
passent par le validateur spécialisé. L'exclusion reste étroite —
`rbac-matrix.json`, `data-classification.json`, `external-flows.json`,
`log-sentinel-observations.json` et `secret-scan-summary.json` restent scannés.

Au passage, la politique d'exclusion était **dupliquée** : `fichiers_a_scanner()`
appliquait sa propre condition, `exclu_du_scan()` une autre. Les motifs de
fichiers ne s'appliquaient donc qu'au rapport Gitleaks, pas à la liste donnée à
`detect-secrets`, et les deux outils auraient cessé de parler du même périmètre.
Une seule fonction fait désormais foi, et un test l'exige.

### Ce que les exclusions ne sont pas

`.secrets.baseline` et `docs/governance/SECRET_SCAN_EXCEPTIONS.json` restent
soustraits aux règles générales d'entropie, **pour une raison unique** : ils
contiennent des empreintes, et un scanner qui les relit signale les siennes à
l'infini.

Cette exclusion ne dit rien de leur contenu, et **aucune exemption ne s'appuie
sur leur emplacement** — un chemin dans `docs/` ne rend pas un contenu
inoffensif. Le validateur spécialisé refuse dans ces deux fichiers : tout champ
`Secret`, `Match`, `Value`, `Raw` ou `Plaintext` ; toute clé privée PEM ; tout
JWT ; toute clé d'accès cloud reconnaissable ; toute URL portant des
identifiants ; toute adresse électronique recopiée d'un rapport ; toute entrée
sans justification ; toute empreinte au format invalide ; tout champ hors
schéma.

### Une sixième correction — les résolutions de fusion

**`reachable = merges + non_merges` est une identité arithmétique.** Elle dit
que la partition est cohérente ; elle ne dit rien sur ce qui a été **lu**.
Le §D du rapport précédent la présentait comme une preuve de couverture. C'en
était une de comptage.

Gitleaks s'appuie sur `git log -p`, qui **n'émet aucun patch pour un commit de
fusion** sans `-m` ni `--cc`. Un contenu introduit pendant une résolution de
conflit — donc absent des deux parents — n'apparaît alors dans aucun patch : ni
dans celui de la fusion, qui n'existe pas, ni dans ceux des parents, qui ne le
contiennent pas.

**Mesuré sur un dépôt jetable**, une valeur présente uniquement dans l'arbre
d'un commit de fusion :

| `git log -p …` | Résolution de fusion | Commit ordinaire |
| --- | :-: | :-: |
| `--all` — *la commande d'origine* | **ABSENT** | DÉTECTÉ |
| `--all --no-merges` | **ABSENT** | DÉTECTÉ |
| `--all --merges` | **ABSENT** | — |
| `--all --merges -m` | **DÉTECTÉ** | — |
| `--all --merges --cc` | **DÉTECTÉ** | — |

Deux scans distincts sont donc exécutés, chacun avec sa propre sonde :

```
ORDINARY_LOG_OPTS = "--all --no-merges"
MERGE_LOG_OPTS    = "--all --merges -m"
```

`-m` est préféré à `--cc` bien que les deux détectent : `-m` produit des diffs
**ordinaires**, un par parent, là où `--cc` produit un diff *combiné* dont
l'analyse par le lecteur de Gitleaks n'est pas garantie. La sonde M2 exerce de
toute façon la variante **réellement utilisée** : si elle ne détecte rien, le
job passe au rouge sous `MERGE_HISTORY_SCAN_INCOMPLETE`. Le choix ne repose
donc pas sur la documentation, mais sur une mesure qui se refait à chaque
exécution.

**Une erreur de méthode, dans ma première reproduction.** J'avais fait
supprimer la sentinelle par un commit **ordinaire**. La suppression la réexpose
dans le diff de ce commit, et `--no-merges` la « détectait » — non parce qu'il
lit les fusions, mais parce qu'il lit une suppression. La sonde passait au vert
sans rien prouver. L'isolation correcte exige qu'**aucun commit ordinaire ne
touche la valeur**, ni pour l'ajouter, ni pour la supprimer.

### Les quatre sondes

| Sonde | Ce qu'elle exerce | Verdict attendu |
| --- | --- | --- |
| **M1** | secret ajouté puis supprimé, hors de toute fusion | détecté par le scan ordinaire |
| **M2** | secret présent uniquement dans l'arbre d'un commit de fusion | détecté par le scan des fusions |
| **M3** | fusion propre, sans sentinelle | aucun faux positif |
| **M4** | arbre courant des dépôts porteurs | propre |

M2 vérifie sa propre prémisse avant de conclure : la valeur doit être dans
l'arbre de la fusion, **absente des deux parents**, et `HEAD` doit rester
propre. Une sonde dont la prémisse est fausse ne prouve rien.

### Non-vacuité de l'historique

La sonde positive ajoute la sentinelle dans un premier commit, **la retire dans
un second**, puis scanne. À `HEAD`, l'arbre du dépôt jetable est propre : une
sonde positive qui réussit ne peut réussir que parce que l'**historique** a
réellement été parcouru. Un scan limité à l'arbre échouerait ici.
