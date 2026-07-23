# Incident du worker planifié — 23 juillet 2026

## Résumé

La tâche Windows `\RuggyLab Report Delivery Outbox Worker` vise le worker
persistant de diffusion des comptes-rendus. Elle n'assure ni les sauvegardes, ni
la purge des jetons, ni l'ingestion automate.

La définition installée et le code actuellement présent dans son répertoire de
travail ne sont plus compatibles :

- la tâche passe `--log-file` ;
- `scripts/process_report_delivery_outbox.py` n'accepte que `--limit`,
  `--max-attempts`, `--interval` et `--once` ;
- le checkout d'origine a quitté, le 8 juillet 2026, la branche qui avait
  temporairement ajouté `--log-file` ;
- le dernier journal de succès observé date du 8 juillet 2026 à 10:17:56.

Le `LastTaskResult=2` observé au début de l'enquête est donc expliqué avec un
niveau de confiance élevé par l'échec d'analyse des arguments. Depuis, les
déclenchements automatiques ont produit d'autres codes. Une tentative automatique
observée entre 22:32:53 et 22:42:53 UTC est restée pendante jusqu'à la limite
d'exécution de dix minutes. Les deux PID visibles formaient une seule chaîne :
le lanceur de la venv était le parent de l'interpréteur Python réel. Une
occurrence intermédiaire a été refusée avec `0x800710E0`, résultat cohérent avec
`IgnoreNew`. Après la limite, la tâche était `Ready`, sans processus correspondant
et avec `0xC000013A`. L'historique opérationnel du Planificateur est désactivé ;
le point exact où l'exécution est restée pendante et son initiateur de terminaison
ne sont donc pas prouvés.

**Décision : ne pas redémarrer ni réenregistrer la tâche en l'état.**

## Chronologie vérifiable

| Date/heure | Fait | Source |
|---|---|---|
| 26 juin 2026 | Création du fichier de tâche Windows. | Métadonnées de la tâche. |
| 28 juin 2026 | Dernière modification de la tâche ; déclencheur toutes les cinq minutes. | `Get-ScheduledTask`, XML de tâche. |
| 28 juin 2026 | Création du journal `logs/report-delivery-worker.log`. | Métadonnées du fichier. |
| 8 juillet 2026 10:17:56 | Dernière ligne de succès observée : compteurs à zéro. | Journal, lecture limitée aux lignes de synthèse. |
| 8 juillet 2026 11:19:16 | Le checkout d'origine quitte la branche qui supportait `--log-file`. | Reflog Git local. |
| Audit antérieur au 23 juillet | Deux PID Python attribués au worker ont été arrêtés par erreur pendant une investigation. | Journal de mission. Leur relation launcher/enfant n'est pas prouvée. |
| 23 juillet 2026 | `LastTaskResult=2`, tâche prête, 47 exécutions manquées dans un état antérieur. | `Get-ScheduledTaskInfo`. |
| 23 juillet 2026 | Un déclenchement automatique est observé sans action de l'auditeur ; la tâche reste active jusqu'à sa limite de dix minutes. | État tâche/processus. |
| 23 juillet 2026 22:21:41 UTC | Tâche `Ready`, aucun worker actif, résultat `0x00041306`, 13 exécutions manquées. | Dernier contrôle lecture seule de cette mission. |
| 23 juillet 2026 22:38:35 UTC | Tâche `Running` ; un lanceur venv et son interpréteur enfant exécutent la même commande depuis 22:32:53/22:33:27. Une occurrence est refusée avec `0x800710E0` et `IgnoreNew`. | `Get-ScheduledTaskInfo`, relation `ParentProcessId`. |
| 23 juillet 2026 22:44:43 UTC | Tâche revenue `Ready`, aucun worker actif, résultat `0xC000013A` après la fenêtre de dix minutes, prochaine tentative automatique annoncée à 22:47:52. | Contrôle lecture seule après la limite d'exécution. |

Les horodatages décrivent les preuves disponibles ; ils ne prouvent pas que le
worker a fonctionné sans interruption avant le 8 juillet.

## Processus arrêtés

Deux processus Python ont été terminés par erreur lors d'une investigation
antérieure. Les PID ne sont pas repris ici car ils ne sont plus actifs et ne
constituent pas un identifiant durable. La présence simultanée de deux PID ne
prouve pas deux instances métier : l'un pouvait être le lanceur de l'autre.

Ce mécanisme a été confirmé lors de la tentative de 22:32:53 : le processus de
la venv était le parent direct de l'interpréteur Python système. Deux PID
n'étaient donc qu'une seule exécution logique. Aucun second worker indépendant
n'a été observé. Cette conclusion reste ponctuelle et n'exclut pas un autre
mécanisme sur un environnement non inspecté.

La tâche est configurée avec `MultipleInstances=IgnoreNew`, ce qui réduit le
risque de deux instances issues de cette tâche. Cela n'exclut pas un worker lancé
manuellement, par un conteneur ou par une autre tâche.

## Tâche concernée

| Élément | Valeur observée |
|---|---|
| Nom complet | `\RuggyLab Report Delivery Outbox Worker` |
| Rôle | Diffusion des entrées persistées de l'outbox de comptes-rendus. |
| Exécutable | `.venv\Scripts\python.exe` du checkout d'origine. |
| Script | `scripts\process_report_delivery_outbox.py` du checkout d'origine. |
| Arguments installés | `--once --limit 50 --max-attempts 8 --log-file <journal>` |
| Répertoire de travail | Checkout d'origine, qui contient des modifications locales préexistantes. |
| Déclencheur | Toutes les cinq minutes. |
| Limite d'exécution | Dix minutes. |
| Instances | `IgnoreNew`. |
| Compte | Utilisateur local interactif, privilèges limités ; identifiant non reproduit. |

Le script courant ouvre une session SQLAlchemy, traite des lignes
`pending`/`failed`, appelle un dispatcher puis commite les nouveaux statuts. Les
dispatchers peuvent produire des effets externes : fichier, FHIR, courriel ou
notification interne.

## Preuves

1. `scripts/process_report_delivery_outbox.py:48-53` définit les quatre options
   acceptées et ne contient pas `--log-file`.
2. `scripts/install_report_delivery_worker_task.ps1:34-46` construit aujourd'hui
   une action sans `--log-file`, toutes les cinq minutes, avec `IgnoreNew` et une
   limite de dix minutes.
3. La définition Windows installée contient encore `--log-file`.
4. Le commit `40c4c7a` d'une autre branche avait ajouté `--log-file` et
   `--check`, ce qui explique l'origine de la définition installée.
5. Le journal n'a plus été alimenté après le changement de branche du checkout.
6. Docker n'était pas actif pendant l'enquête ; aucun conteneur doublon n'a été
   trouvé. Cette observation ponctuelle n'est pas une garantie durable.
7. Une tentative automatique a créé une chaîne lanceur/interpréteur unique,
   est restée pendante jusqu'à la limite de dix minutes puis a disparu sans
   intervention de l'auditeur.
8. Le refus `0x800710E0` pendant cette fenêtre est cohérent avec le couple
   `Running`/`IgnoreNew` ; il ne démontre pas l'état de la file d'outbox.

## Impact probable

| Impact | Évaluation |
|---|---|
| Retard de diffusion | Plausible et élevé si l'outbox contient des éléments. |
| File d'attente | Plausible ; le volume réel est inconnu car aucune base n'a été interrogée. |
| Perte de notification | Non prouvée. L'outbox persistante protège les entrées déjà committées. |
| Duplication | Possible lors d'une reprise concurrente ou après effet externe sans statut committé. |
| Sauvegarde absente | Non : ce worker n'est pas le service de sauvegarde. |
| Purge absente | Non : ce worker n'est pas le scheduler de purge. |
| Risque clinique | Retard possible de remise d'un compte-rendu ; aucun cas réel n'a été consulté. |

## Risque de non-redémarrage

- accumulation des entrées `pending` ou `failed` ;
- retard de livraison des comptes-rendus ;
- absence de reprise des erreurs transitoires ;
- croissance de l'outbox et perte de visibilité opérationnelle.

Le volume, l'âge et les destinations concernés restent **inconnus** sans une
requête agrégée autorisée sur l'environnement d'exploitation.

## Risque de redémarrage

Un redémarrage inchangé est inutile : l'argument non reconnu demeure. Une
remise en service mal contrôlée peut également :

- lancer un second worker déjà présent ailleurs ;
- rejouer un effet externe dont le statut n'a pas été committé ;
- créer une duplication, car le traitement courant ne prend pas les lignes avec
  `FOR UPDATE SKIP LOCKED` ;
- utiliser un checkout mutable et une venv qui ne correspondent pas au SHA
  qualifié ;
- masquer l'échec faute d'historique de tâche et de journal compatible.

Les déclenchements automatiques restant actifs, une nouvelle tentative pendante
peut apparaître sans redémarrage manuel. Il ne faut ni lancer un passage
supplémentaire ni modifier l'instance en cours sans l'autorisation et les
contrôles décrits ci-dessous.

## Commandes de vérification en lecture seule

Ces commandes ne doivent afficher que des métadonnées et des compteurs. Toute
sortie contenant un principal doit être expurgée avant partage.

```powershell
$taskName = "RuggyLab Report Delivery Outbox Worker"
Get-ScheduledTask -TaskName $taskName
Get-ScheduledTaskInfo -TaskName $taskName

Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and
    $_.CommandLine -like '*process_report_delivery_outbox.py*'
  } |
  Select-Object ProcessId, ParentProcessId, CreationDate
```

Pour le journal, limiter la lecture aux lignes de compteurs et ne jamais copier
un payload :

```powershell
Select-String -LiteralPath "<journal>" `
  -Pattern 'processed=\d+ retried=\d+ dead_lettered=\d+ skipped=\d+' |
  Select-Object -Last 20
```

La vérification de l'outbox doit être une requête agrégée approuvée, sans contenu
de compte-rendu ni identifiant patient : compte par statut, plus ancien
horodatage et nombre au-delà du nombre maximal de tentatives.

## Procédure proposée de remise en service

Cette procédure est **préparée mais non exécutée**. Elle requiert
l'autorisation explicite de modifier/redémarrer la tâche.

1. Désigner un SHA de release qualifié et un répertoire immuable distinct du
   checkout de développement.
2. Créer et qualifier une venv propre à ce SHA.
3. Exporter la définition actuelle dans un emplacement protégé pour rollback ;
   expurger le principal dans toute copie vers le dossier de preuve.
4. Vérifier qu'aucun autre processus, service ou conteneur n'assure le même rôle.
5. Relever uniquement les compteurs agrégés de l'outbox.
6. Réenregistrer la tâche avec
   `scripts/install_report_delivery_worker_task.ps1` depuis la release retenue,
   ou appliquer une action strictement équivalente à :

```text
<release>\.venv\Scripts\python.exe
<release>\scripts\process_report_delivery_outbox.py --once --limit 50 --max-attempts 8
```

7. Effectuer d'abord un passage unique supervisé, tâche récurrente désactivée.
8. Vérifier les compteurs, les statuts, les erreurs et l'absence de doublon.
9. Activer ensuite le déclencheur de cinq minutes.
10. Activer l'historique opérationnel du Planificateur ou une journalisation
    structurée qualifiée, sans payload clinique.

## Contrôles post-redémarrage

- une seule instance active ;
- durée inférieure à la limite de dix minutes ;
- code de sortie nul ;
- décrément contrôlé des `pending` sans hausse anormale des `dead_letter` ;
- aucun envoi doublon sur un jeu synthétique ou une file de qualification ;
- métrique/alerte sur l'âge de la plus ancienne entrée ;
- journal sans payload, secret ni donnée patient ;
- déclenchement suivant exécuté une seule fois.

## Rollback

1. Désactiver le déclencheur nouvellement modifié sans supprimer la file.
2. Arrêter uniquement le PID préalablement attribué à cette tâche.
3. Conserver toutes les lignes d'outbox et leurs tentatives.
4. Restaurer la définition exportée seulement si elle pointe vers une paire
   code/arguments compatible ; sinon laisser la tâche désactivée.
5. Revenir à la release précédente par répertoire/SHA, jamais en réécrivant un
   checkout mutable.
6. Comparer les compteurs avant/après et ouvrir un incident pour toute
   destination dont l'état est ambigu.

## Conclusion et décision requise

La cause la plus probable du code `2` est confirmée statiquement : incompatibilité
entre l'action installée et l'interface CLI courante. Le backlog et l'impact réel
ne sont pas connus. La paire de PID observée était une seule chaîne
lanceur/interpréteur, pas deux workers indépendants. Elle est restée pendante
jusqu'à la limite de dix minutes avant de disparaître. Aucun doublon indépendant
n'a été observé, mais l'absence ponctuelle de processus ne garantit pas l'absence
d'un autre mécanisme. Le prochain déclenchement automatique peut reproduire le
cycle tant que la définition installée reste active et incompatible.

Autorisation exacte attendue :

> Autoriser la modification de `\RuggyLab Report Delivery Outbox Worker` pour la
> faire pointer vers une release immuable au SHA approuvé, retirer l'argument
> incompatible, effectuer un seul passage supervisé après vérification des
> doublons et compteurs agrégés, puis réactiver le déclencheur uniquement si les
> contrôles post-redémarrage sont conformes.
