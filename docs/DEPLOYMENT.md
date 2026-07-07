# Mise en production (go-live) — RuggyLab OS

Procédure de déploiement réel sur **PostgreSQL**, avec checklist de mise en
service. Cible : un serveur Linux avec Docker, ou une machine Windows (scripts
PowerShell fournis). Pour les tests métier sans installation, voir [UAT.md](UAT.md).

> Données patients réelles : instance dédiée, accès restreints, audit activé,
> sauvegardes testées. Ne jamais réutiliser les mots de passe de démo.

## 1. Pré-requis

- Docker + Docker Compose (recommandé) — ou Python 3.13 + PostgreSQL 16 + Redis 7.
- Un nom de domaine + TLS (reverse proxy : Caddy/Nginx/Traefik) devant l'app.
- Secrets générés (voir [SECRETS_MANAGEMENT.md](SECRETS_MANAGEMENT.md)).

## 2. Configuration (.env)

Copier `.env.example` → `.env` et renseigner **au minimum** :

```dotenv
SECRET_KEY=<chaîne aléatoire >= 32 caractères, unique>
FIRST_SUPERUSER_PASSWORD=<mot de passe fort >= 16 caractères>
POSTGRES_PASSWORD=<mot de passe PostgreSQL>
DATABASE_URL=postgresql+psycopg://ruggylab:<POSTGRES_PASSWORD>@postgres:5432/ruggylab
REDIS_URL=redis://redis:6379/0
CACHE_BACKEND=redis
GRAFANA_PASSWORD=<mot de passe Grafana>
```

Générer une clé : `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## 3. Démarrage (Docker Compose)

```bash
docker compose up -d postgres redis        # dépendances
docker compose --profile migrate up migrate  # alembic upgrade head (run-once)
docker compose up -d app prometheus grafana  # application + supervision
```

Sans Docker (Windows) : voir `scripts/install.ps1` et `scripts/start.ps1`.

### Worker de diffusion des comptes-rendus (Windows)

Installer la tâche avec le même compte Windows et le même répertoire `.env` que
l'application. L'installation vérifie d'abord la connexion à la base et refuse
d'enregistrer une tâche non fonctionnelle :

```powershell
.\scripts\install_report_delivery_worker_task.ps1 -RunNow
Get-ScheduledTaskInfo -TaskName "RuggyLab Report Delivery Outbox Worker"
Get-Content .\logs\report-delivery-worker.log -Tail 30
```

Le code `LastTaskResult = 0` et une ligne récente
`report outbox processed=...` dans le journal confirment le passage. La tâche
ignore un nouveau lancement si le précédent travaille encore. Pour la retirer :

```powershell
.\scripts\uninstall_report_delivery_worker_task.ps1
```

Après déplacement du dépôt, changement de compte de service, de Python ou de
`.env`, réinstaller la tâche afin d'actualiser ses chemins absolus. Pour un
serveur où aucun utilisateur ne reste connecté, configurer ensuite la tâche dans
le Planificateur Windows avec un compte de service autorisé à « ouvrir une
session en tant que tâche » et l'option d'exécution hors connexion.

## 4. Vérification de prêt-au-déploiement (automatique)

Sur l'instance cible, **mêmes variables d'environnement que le serveur** :

```bash
python -m scripts.check_deploy_readiness
```

Contrôle : SECRET_KEY/mot de passe admin robustes, base PostgreSQL accessible,
**migrations à jour**, mot de passe admin non par défaut. Sortie 0 = prêt.

Puis le smoke test bout-en-bout (flux labo complet) :

```bash
UAT_BASE_URL=https://votre-domaine python -m scripts.uat_smoke
```

## 5. Checklist go-live

- [ ] `.env` renseigné ; secrets forts (jamais les valeurs de démo).
- [ ] `DATABASE_URL` pointe sur PostgreSQL (pas SQLite).
- [ ] `alembic upgrade head` exécuté ; `check_deploy_readiness` → **PRÊT**.
- [ ] **Mot de passe admin changé** dès la 1re connexion (le défaut de test est refusé par le contrôle).
- [ ] Référentiels initialisés : `bioref/seed-defaults`, `tariffs/seed-defaults` (prix ajustés), cibles TAT.
- [ ] Comptes nominatifs créés par rôle (technician/officer/accountant) ; pas de comptes partagés.
- [ ] TLS actif devant l'app ; ports internes (5432/6379/9090) non exposés publiquement.
- [ ] **Sauvegarde testée** : `scripts/pg_backup.ps1` puis **restauration vérifiée** `scripts/pg_restore_verify.ps1` → verdict `SUCCÈS` sur base scratch (§6).
- [ ] Supervision : Prometheus/Grafana accessibles, alertes configurées (voir [observability.md](observability.md)).
- [ ] Audit activé et consultable (rôle admin).
- [ ] `uat_smoke` → **15/15** contre l'instance de prod (sur données de test, à nettoyer ensuite via `scripts/cleanup_uat_data.py`).
- [ ] Plan de rollback connu (§7).

## 6. Sauvegarde & restauration

**Production (PostgreSQL)** — `pg_dump` format custom, empreinte SHA-256, rétention,
marqueur de dernier succès :

```powershell
# Sauvegarde PostgreSQL — planifier en tâche récurrente (chiffrement optionnel)
./scripts/pg_backup.ps1 -RetentionDays 14            # ajouter -Encrypt + $env:BACKUP_PASSPHRASE
# Restauration VÉRIFIÉE sur base scratch (les 8 étapes du §28 : schéma, head Alembic,
# comptes, volumes, smoke test) ; la base de production n'est jamais touchée :
./scripts/pg_restore_verify.ps1 -BackupFile backups/ruggylab_pg-YYYYMMDD-HHMMSS.dump
```

Le verdict `SUCCÈS` du rapport (`artifacts/restore-verify-*.txt`) est la **seule**
preuve qu'une sauvegarde est exploitable : une sauvegarde non restaurée n'est pas
une sauvegarde. Copier les dumps **hors-site** (disque chiffré / 4G).

> **Développement local (SQLite)** : `scripts/backup.ps1` / `scripts/restore.ps1`
> font une simple copie du fichier `.db` — réservés au poste de dev, **pas** à la prod.

## 7. Rollback

- **Applicatif** : redéployer l'image précédente (`ghcr.io/.../ruggylab-os:<sha|tag>` antérieur).
- **Schéma** : les migrations sont idempotentes ; un `alembic downgrade <rev>` est
  possible mais privilégier la restauration d'une sauvegarde si des données ont
  été écrites. Toujours sauvegarder avant `upgrade`.

## 8. Intégration continue (rappel)

`.github/workflows/ci.yml` verrouille déjà : ruff (lint+format), mypy, bandit,
pytest, **migrations + idempotence + smoke sur PostgreSQL réel**, CodeQL, et
publie l'image Docker sur tag `vX.Y.Z`. Ne déployer qu'un commit dont la CI est verte.
