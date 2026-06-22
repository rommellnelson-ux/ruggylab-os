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
- [ ] **Sauvegarde testée** : `scripts/backup.ps1` puis **restauration** `scripts/restore.ps1` validée sur une instance jetable (§6).
- [ ] Supervision : Prometheus/Grafana accessibles, alertes configurées (voir [observability.md](observability.md)).
- [ ] Audit activé et consultable (rôle admin).
- [ ] `uat_smoke` → **15/15** contre l'instance de prod (sur données de test, à nettoyer ensuite via `scripts/cleanup_uat_data.py`).
- [ ] Plan de rollback connu (§7).

## 6. Sauvegarde & restauration

```powershell
# Sauvegarde (pg_dump) — planifier en tâche récurrente
./scripts/backup.ps1
# Restauration sur une instance de validation (jamais la prod en premier)
./scripts/restore.ps1 -BackupFile <fichier>
```

Tester la restauration **avant** le go-live : une sauvegarde non restaurée n'est
pas une sauvegarde.

## 7. Rollback

- **Applicatif** : redéployer l'image précédente (`ghcr.io/.../ruggylab-os:<sha|tag>` antérieur).
- **Schéma** : les migrations sont idempotentes ; un `alembic downgrade <rev>` est
  possible mais privilégier la restauration d'une sauvegarde si des données ont
  été écrites. Toujours sauvegarder avant `upgrade`.

## 8. Intégration continue (rappel)

`.github/workflows/ci.yml` verrouille déjà : ruff (lint+format), mypy, bandit,
pytest, **migrations + idempotence + smoke sur PostgreSQL réel**, CodeQL, et
publie l'image Docker sur tag `vX.Y.Z`. Ne déployer qu'un commit dont la CI est verte.
