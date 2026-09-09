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

Deux fichiers sont exclus du scan : `.secrets.baseline` et le registre
lui-même. Ils ne contiennent que des empreintes ; les scanner ferait relever ces
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
| — couvertes par le registre d'exceptions | **161** |
| — **sans couverture écrite** | **0** |

Par règle : `Secret Keyword` 197, `Basic Auth Credentials` 22,
`Hex High Entropy String` 10.

Par famille, pour les 161 entrées du registre : `tests` 130, `ci_jetable` 14,
`empreintes_publiques` 7, `documentation` 7, `scripts_utilitaires` 2,
`generateurs_g0` 1.

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

<!-- MESURE_HISTORIQUE_GITLEAKS -->
Résultat mesuré sur la CI : voir §6.3.

### 6.3 Verdict des sondes

<!-- MESURE_SONDES -->
Verdicts mesurés sur la CI : voir le journal du job.

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
