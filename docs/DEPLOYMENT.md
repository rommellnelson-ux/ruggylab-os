# Mise en production (go-live) — RuggyLab OS

Procédure de déploiement réel sur **PostgreSQL**, avec checklist de mise en
service. Cible : un serveur Linux avec Docker, ou une machine Windows (scripts
PowerShell fournis). Pour les tests métier sans installation, voir [UAT.md](UAT.md).

> Données patients réelles : instance dédiée, accès restreints, audit activé,
> sauvegardes testées. Ne jamais réutiliser les mots de passe de démo.

## 1. Pré-requis

- Docker + Docker Compose (recommandé) — ou Python 3.13 + PostgreSQL 16 + Redis 7.
- Un nom de domaine (ou nom d'hôte LAN). Le reverse proxy TLS **Caddy est intégré**
  au compose (service `proxy`, seul service exposé : 80→443) ; pas besoin d'en
  installer un séparément.
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
RUGGYLAB_DOMAIN=<domaine ou nom d'hôte servi par le proxy, ex. labo.exemple.ci>
# Artefact immuable : TOUJOURS un tag précis publié par la CI, jamais `latest`.
RUGGYLAB_IMAGE=ghcr.io/rommellnelson-ux/ruggylab-os:<git-sha ou vX.Y.Z>
```

> `REQUIRE_VALIDATION_FOR_RELEASE` vaut `true` par défaut en production (aucun
> compte-rendu publié sans validation biologique). Ne le désactiver qu'avec une
> procédure « provisoire » écrite et approuvée.

Générer une clé : `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## 3. Démarrage (Docker Compose)

```bash
docker compose up -d postgres redis           # dépendances
docker compose --profile migrate run --rm migrate  # alembic upgrade head (run-once)
docker compose up -d                          # proxy + app + workers + supervision
```

> **Production = `docker-compose.yml` seul.** Les surcharges de développement
> vivent dans `docker-compose.dev.yml` et ne sont **jamais** chargées
> implicitement (l'ancien nom `docker-compose.override.yml` était fusionné en
> silence par Compose et annulait l'architecture de production : `--reload`,
> rôle `all` dupliquant les singletons, ports techniques réouverts).
>
> Développement local :
> `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`

L'accès utilisateur se fait **uniquement** via `https://$RUGGYLAB_DOMAIN` (le proxy
Caddy termine le TLS et redirige 80→443). Aucun autre port n'est publié : app,
PostgreSQL, Redis, Prometheus et Grafana ne sont joignables que sur les réseaux
internes. Prometheus/Grafana s'atteignent via VPN/bastion (voir §8/9 des
Instructions maîtres et `deploy/Caddyfile`).

> TLS : par défaut le proxy utilise une **CA interne** (site LAN sans Internet —
> installer le certificat racine Caddy sur les postes). Pour un domaine public,
> voir les options ACME/certificats dans `deploy/Caddyfile`.

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
- [ ] Proxy Caddy actif (TLS) ; **seuls 80/443 publiés**. app (8000), PostgreSQL (5432), Redis (6379), Prometheus (9090), Grafana (3000) non exposés — `docker compose ps` / `ss -lntp` pour vérifier.
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
