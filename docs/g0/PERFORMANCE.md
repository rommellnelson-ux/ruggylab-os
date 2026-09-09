# G0 — Baseline de performance (preuve 8)

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

> **Aucun objectif de latence.** Une latence élevée est un résultat, pas un
> échec. Le seul verdict que porte cette campagne concerne la **validité de la
> mesure** : une mesure dont on ne pourrait rien conclure fait échouer le job ;
> un chiffre déplaisant, jamais.
>
> Mesuré par la CI Linux (`.github/workflows/g0-quality.yml`, job
> **G0 — Performance baseline**) au moyen de
> [`scripts/g0_perf_baseline.py`](../../scripts/g0_perf_baseline.py).

## 1. Pourquoi un banc qui n'échoue pas sur les chiffres

Un banc d'essai qui échoue quand les chiffres déplaisent finit par être réglé
pour plaire : on réduit le scénario, on retire l'écriture, on relance jusqu'à
obtenir une bonne série. La baseline décrit alors un système qui n'existe pas,
et personne ne s'en aperçoit parce qu'elle est verte.

Les contrôles portent donc ailleurs — sur ce qui rendrait la mesure
inexploitable :

| Motif d'invalidité | Ce qu'il empêche de croire |
| --- | --- |
| Application non saine avant ou après | Que les chiffres décrivent un système en état de marche |
| Scénario non terminé (aucune réponse en succès) | Qu'un parcours mesuré ait réellement abouti |
| Authentification impossible | Que la charge ait été appliquée sur des routes protégées |
| Données non synthétiques détectées | Que la mesure n'ait pas touché de données réelles |
| Échantillons insuffisants | Qu'un centile sur trois valeurs signifie quelque chose |
| Horloge non monotone | Que les durées soient comparables entre elles |
| Résultat incomplet (p50/p95/p99, débit, provenance) | Que la mesure se rejoue et se compare |
| Environnement non décrit | Que la baseline se compare à quoi que ce soit |
| Interrupteur externe actif (CSA, automate) | Que ce soit le laboratoire, et lui seul, qui ait été mesuré |
| Erreur effacée de l'agrégat, ou réessai déclaré | Que le taux d'erreur publié soit le taux d'erreur observé |

## 2. Stack mesurée

La stack Docker réelle, démarrée depuis `docker-compose.yml` — l'image est
construite dans le job, son identifiant et l'empreinte de son archive sont
enregistrés dans la provenance.

| Service | Rôle dans la mesure |
| --- | --- |
| `proxy` (Caddy) | Terminaison TLS ; la charge entre par où entre un poste du laboratoire |
| `app` | Application mesurée, rôle `web` |
| `scheduler` | Rôle planificateur, présent car il partage la base |
| `analyzer-gateway` | Présent, **interfaces automates désactivées** |
| `postgres` | PostgreSQL 16, base migrée avant la mesure |
| `valkey` | Cache et compteurs |
| `prometheus` | Supervision interne |
| `db-backup` | Sauvegarde périodique, laissée en place : elle existe en exploitation |
| `grafana` | **Non requis, non démarré** — et le job le vérifie |

### Ce que la mesure désactive, et ce que cela coûte

[`scripts/g0_perf_overlay.yml`](../../scripts/g0_perf_overlay.yml) désactive les
deux limiteurs de débit, et rien d'autre :

```yaml
RATE_LIMIT_ENABLED: "false"
LOGIN_RATE_LIMIT_ENABLED: "false"
```

En production, `RATE_LIMIT_REQUESTS=100` par tranche de 60 s et
`LOGIN_RATE_LIMIT_REQUESTS=10` par tranche de 300 s s'appliquent **par adresse
IP**. Un banc d'essai lancé depuis une seule machine partage forcément une seule
adresse : une première exécution l'a confirmé — 77 réponses `429` sur
129 requêtes, et 100 % d'erreurs dès deux utilisateurs simultanés. On ne
mesurait plus le laboratoire, on mesurait le limiteur.

> **Conséquence à retenir, et à instruire au lot D.** Les chiffres publiés ici
> décrivent l'application **sans** ce limiteur. Le limiteur, lui, reste actif en
> exploitation et plafonne le débit soutenu à environ **1,7 requête par seconde
> et par adresse IP** — très en dessous des débits mesurés. Ce n'est pas un
> détail de configuration : tous les postes d'un laboratoire situés derrière un
> même proxy partagent cette adresse. L'état réel des deux réglages est
> enregistré dans `perf-baseline.json`
> (`environment.application_configuration`) : la mesure dit ce qu'elle a
> désactivé, elle ne le dissimule pas.

### Aucun système externe

CSA et interfaces d'automates restent désactivés. Le script ne se contente pas
de lire les variables d'environnement du conteneur : une variable **absente** ne
dit pas « false », elle ne dit rien. Il interroge donc le processus applicatif
lui-même et publie les valeurs effectives dans
`environment.effective_external_switches` :

```
CSA_SYNC_ENABLED = false
ENABLE_DH36_LISTENER = false
ANALYZER_RAW_LISTENER_ENABLED = false
```

Une seule de ces valeurs à `true` invalide la mesure.

## 3. Scénario

Quatorze pas, dans cet ordre, déroulés intégralement à chaque itération de
chaque utilisateur virtuel. Une lecture isolée ne dirait rien d'un laboratoire,
où lire suppose que quelqu'un a écrit juste avant.

| # | Pas | Genre | Route |
| --- | --- | --- | --- |
| 1 | Authentification | lecture | `POST /api/v1/login/access-token` |
| 2 | Création patient | écriture | `POST /api/v1/patients` |
| 3 | Recherche patient | lecture | `GET /api/v1/patients?q=…` |
| 4 | Prescription (NFS + GE) | écriture | `POST /api/v1/exam-orders` |
| 5 | Échantillon (code-barres) | écriture | `POST /api/v1/samples` |
| 6 | Rattachement échantillon | écriture | `POST /api/v1/exam-orders/{id}/collect` |
| 7 | File de travail | lecture | `GET /api/v1/worklist/my` |
| 8 | Consultation d'un ordre | lecture | `GET /api/v1/exam-orders/{id}` |
| 9 | Saisie d'un résultat | écriture | `POST /api/v1/results` |
| 10 | Consultation d'un résultat | lecture | `GET /api/v1/results/{id}` |
| 11 | Libération du compte rendu | écriture | `POST /api/v1/reports/results/{id}/release` |
| 12 | Tableau de bord | lecture | `GET /api/v1/stats/summary` |
| 13 | Facture fictive | écriture | `POST /api/v1/invoices` |
| 14 | Encaissement fictif | écriture | `POST /api/v1/invoices/{id}/payments` |

La facturation passe par un **compte comptable dédié**, créé une fois avant la
mesure : le cloisonnement est réel, un administrateur n'accède pas à la
facturation. Le créer dans la boucle aurait fait passer une création
d'utilisateur pour de la facturation.

Le parcours porte une **empreinte SHA-256** (`run.scenario_sha256`) calculée sur
les noms, genres, méthodes et gabarits d'URL. Changer une route, en retirer un
pas ou en changer l'ordre change cette valeur, et la provenance devient
incohérente avec la mesure — c'est ce qui empêche de republier une baseline
décrivant un parcours qu'on n'exécute plus.

### Données

Strictement synthétiques, et **vérifiées** plutôt que supposées. Tout
identifiant créé porte le préfixe `G0SYNTH-<run_id>-…` ; les noms sont tirés
d'un vocabulaire fermé et manifestement fictif (`Alpha`, `Bravo`, `Charlie`,
`Delta`, `Echo`, `Foxtrot` / `Temoin`, `Fictif`, `Synthetique`, `Essai`, `Banc`,
`Zero`). Un identifiant sans marque ou un nom hors vocabulaire invalide la
mesure. Le contenu est tiré d'un générateur ensemencé (`--seed 20260909`) ;
seuls les identifiants portent un espace de noms propre à l'exécution, faute de
quoi la deuxième exécution violerait les contraintes d'unicité et l'on
prendrait un conflit de clé pour une régression de performance.

### Charge

| Paramètre | Valeur | Pourquoi |
| --- | --- | --- |
| Niveaux de concurrence | **1, 3, 5, 10** | 3 est le premier usage envisagé au CSA GR Plateau : un guichet, un préleveur, un technicien |
| Répétitions par niveau | **3** | En dessous, la dispersion entre exécutions n'est pas observable |
| Chauffe par utilisateur | **2 itérations** | Non mesurées : connexions TLS et caches en cours d'amorçage |
| Itérations mesurées par utilisateur | **5** | Voir la note ci-dessous |
| Réessais | **0** | Un réessai transformerait 8 % d'erreurs en 0 % apparent |
| Centiles | rang le plus proche, sans interpolation | Sur des effectifs modestes, l'interpolation fabrique des valeurs jamais observées |
| Horloge | `time.perf_counter` (monotone) | Vérifiée : aucune durée nulle ou négative, aucun départ antérieur au début de l'exécution |

> **Ce qui est borné pour tenir en CI, et ce qui ne l'est pas.** Le **scénario
> n'est pas réduit** : les quatorze pas, les quatre niveaux et les trois
> répétitions sont exécutés intégralement. Ce qui est borné, c'est le nombre
> d'itérations mesurées par utilisateur virtuel — **5**, après 2 de chauffe.
> Le prix de ce choix est réel et doit être dit : à concurrence 1, un scénario
> donné n'est observé que 15 fois par niveau, et un p99 sur 15 valeurs est le
> quinzième point de la série, pas une queue de distribution. Les centiles
> élevés des niveaux bas sont donc **indicatifs**, et le contrôle d'effectif
> minimum (10 échantillons par scénario et par niveau) est le plancher en
> dessous duquel la mesure est déclarée invalide plutôt que publiée.

## 4. Résultats mesurés

<!-- RESULTATS_PERFORMANCE_DEBUT -->

*Section renseignée depuis l'exécution de CI identifiée ci-dessous. Tant
qu'aucune exécution n'a produit les artefacts, aucun chiffre ne figure ici :
une estimation vaudrait moins qu'une absence.*

<!-- RESULTATS_PERFORMANCE_FIN -->

## 5. Erreurs applicatives

Une requête qui échoue est **comptée, classée par type, et publiée**. Elle n'est
ni réessayée, ni exclue de l'agrégat. Le contrôle de validité vérifie en outre
que l'agrégat de chaque niveau porte exactement autant d'erreurs que la somme de
ses scénarios, et que `errors_by_type_total` les totalise : une erreur effacée
entre la mesure et le fichier fait échouer le job.

Les erreurs observées relèvent du **lot D**. Elles ne sont pas corrigées ici :
le lot C mesure, et corriger un défaut découvert en le mesurant reviendrait à
publier la mesure d'un système qu'on vient de changer.

## 6. Provenance

`artifacts/g0/perf-provenance.json` porte, pour chaque exécution :

- le commit Git mesuré, le runner, l'OS, l'architecture, le nombre de CPU et la
  mémoire ;
- les versions de Docker, Python, PostgreSQL et Valkey ;
- l'identifiant de l'image mesurée et l'empreinte SHA-256 de son archive ;
- la configuration applicative observée et les interrupteurs externes effectifs ;
- le jeu de données, la graine, l'ordre des scénarios et leur empreinte, les
  niveaux de concurrence, les répétitions, la durée et la commande exacte ;
- l'empreinte SHA-256 des fichiers d'entrée (ensemble `performance` :
  le script de mesure, la surcharge, `app/**`, `alembic/**`,
  `docker-compose.yml`, `Dockerfile`, `requirements.txt`).

Le workflow contrôle **schéma, complétude, cohérence et provenance**. Il ne
compare **jamais** des latences octet à octet : elles varient par nature, et un
tel contrôle échouerait à chaque exécution honnête jusqu'à ce que quelqu'un le
désactive.

## 7. Non-vacuité des contrôles

| Mutation appliquée | Refus attendu |
| --- | --- |
| p99 absent d'un scénario, ou d'un agrégat | `sans p99` / `agregat sans p99` |
| Provenance absente ou incomplète | `provenance sans bloc deterministic` |
| Échantillons sous le minimum déclaré | `sous-echantillonne` |
| Moins de trois répétitions | `moins de trois repetitions` |
| Erreur effacée de l'agrégat | `une erreur a ete masquee` |
| Erreur comptée mais non classée | `classification est incomplete` |
| Réessais déclarés | `des reessais ont eu lieu` |
| Identifiant ou nom non synthétique | `identifiant non synthetique` / `hors vocabulaire` |
| Environnement incomplet | `environnement non decrit` |
| Interrupteur externe actif | `systeme externe actif` |
| Scénario modifié sans changement de son empreinte | `l'empreinte du scenario enregistree n'est pas celle du scenario execute` |
| Référence de branche temporaire comme source | `reference temporaire` |

Chaque mutation est accompagnée d'un **témoin** exigeant l'inverse sur la mesure
intacte, dans
[`tests/test_g0_quality_baseline.py`](../../tests/test_g0_quality_baseline.py).
Les charges utiles y sont construites dans le test, jamais relues dans un
artefact produit avant la mutation.

## 8. Limites

1. **Un runner GitHub partagé n'est pas un serveur de laboratoire.** Les chiffres
   valent comme point de comparaison entre révisions mesurées de la même
   manière, pas comme prédiction du comportement au CSA GR Plateau.
2. **Base vide au départ.** Aucun historique n'est chargé : les temps de requête
   sur des tables de quelques milliers de lignes ne préjugent pas de ceux
   observés après des mois d'exploitation.
3. **Un seul poste de charge.** Le client et la stack partagent la même machine ;
   une part du CPU mesurée côté conteneurs est disputée par le banc lui-même.
4. **Limiteurs désactivés** (§2) : le débit publié n'est pas atteignable en
   exploitation depuis une seule adresse IP.
5. **Cinq itérations mesurées par utilisateur** (§3) : les centiles élevés des
   niveaux de faible concurrence reposent sur des effectifs modestes.
6. **Aucune mesure de la restitution navigateur.** Ce banc mesure l'API. Le temps
   perçu par un utilisateur devant l'interface n'est pas ce qui est publié ici.
