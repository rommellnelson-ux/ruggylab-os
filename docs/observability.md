# Supervision de production

RuggyLab OS expose ses métriques Prometheus sur le port interne `8001`. Le
fichier `monitoring/prometheus.yml` collecte `app:8001/metrics` et charge les
règles de `monitoring/rules/`.

## Vérification

Après `docker compose up -d app prometheus grafana` :

```powershell
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose exec prometheus promtool check rules /etc/prometheus/rules/ruggylab.yml
docker compose exec prometheus wget -qO- http://app:8001/metrics
```

Les interfaces sont volontairement liées à `127.0.0.1` :

- application : `127.0.0.1:8000` ;
- Prometheus : `127.0.0.1:9090` ;
- Grafana : `127.0.0.1:3000`.

Un reverse proxy HTTPS authentifié doit publier l'application. Prometheus ne
doit pas être publié. Grafana peut rester accessible uniquement par VPN ou être
publié par le proxy avec une politique d'accès distincte.

## Alertes fournies

- indisponibilité de l'application pendant deux minutes ;
- taux de réponses 5xx supérieur à 5 % ;
- latence HTTP p95 supérieure à deux secondes ;
- volume anormal d'échecs d'authentification.

Prometheus évalue ces règles mais ne transmet aucune notification tout seul.
Pour envoyer des alertes, déployer Alertmanager, configurer son canal
(courriel/SMS/astreinte), puis activer le bloc `alerting` de
`monitoring/prometheus.yml`. Tester le chemin complet jusqu'au téléphone ou à
la boîte d'astreinte.

## Journaux et données sensibles

Les conteneurs écrivent vers stdout/stderr. Collecter ces flux avec le système
de logs de l'hébergeur, définir rétention et rotation, et alerter sur les erreurs
récurrentes. Ne pas ajouter aux logs les résultats, noms de patients, jetons,
clés d'API ou chaînes de connexion.

## Sauvegardes

Le marqueur `backups/last_success.json` est une preuve locale utile, pas une
alerte distante. Le planificateur doit surveiller le code retour de
`scripts/pg_backup.ps1`, l'âge du marqueur et l'échec de la copie hors site.
Une restauration scratch réussie et datée reste la preuve d'exploitabilité.
