# Qualification du serveur & pilote encadré — RuggyLab OS

Ce document couvre les deux étapes que **seule l'équipe du laboratoire** peut
exécuter, la CI ne pouvant prouver que le logiciel, pas le matériel :

1. **Qualifier le serveur physique** (logiciel + matériel réels).
2. **Lancer un pilote encadré** sans production de résultats officiels.

> Rappel : tout ce qui est marqué « VERIFIED en CI » dans
> [ARCHITECTURE_AS_BUILT.md](ARCHITECTURE_AS_BUILT.md) l'est sur les runners
> GitHub, **pas sur ce serveur**. La qualification ci-dessous transforme ces
> « VERIFIED en CI » en « VERIFIED sur site ».

---

## Partie A — Qualification du serveur

### A.1 Pré-requis matériels (à cocher physiquement)

- [ ] Serveur, switch, proxy/routeur, stockage, **poste de validation** et modem
      4G sur **onduleur (UPS)** — cf. §30. Noter autonomie et date des batteries.
- [ ] Convertisseurs série/IP des automates sur UPS.
- [ ] Interface réseau dédiée au **VLAN automates** identifiée (IP fixe du serveur
      sur ce VLAN) — le réseau Docker `analyzer_net` n'est PAS un VLAN physique.
- [ ] Imprimante(s) étiquettes/CR testée(s).
- [ ] Emplacement **hors-site** pour les sauvegardes (disque chiffré / NAS).

### A.2 Mise en route logicielle

```bash
# 1) Configuration
cp .env.example .env      # renseigner SECRET_KEY, POSTGRES_PASSWORD,
                          # FIRST_SUPERUSER_PASSWORD, GRAFANA_PASSWORD,
                          # RUGGYLAB_DOMAIN, RUGGYLAB_IMAGE (tag précis publié par la CI)

# 2) Dépendances + migrations (run-once)
docker compose up -d postgres redis
docker compose --profile migrate run --rm migrate

# 3) Stack de production complète (fichier de prod SEUL)
docker compose up -d
```

### A.3 Contrôle automatisé (pass/fail)

```bash
RUGGYLAB_DOMAIN=<votre-domaine> ./scripts/qualify_stack.sh
```

Le script vérifie, **sur ce serveur** : services sains, seuls 80/443 publiés,
accès TLS, chemins techniques bloqués (404), schéma migré, dernier backup
intègre, et **flux clinique 15/15 via le proxy**. Sortie 0 = qualifié.

À défaut de Docker/`bash` (Windows nu) : `python -m scripts.check_deploy_readiness`
puis `UAT_BASE_URL=https://<domaine> python -m scripts.uat_smoke`.

### A.4 Contrôles matériels (manuels — la CI ne peut pas les faire)

- [ ] **Sous-réseau proxy** : vérifier que `172.28.117.0/24` (frontend_net)
      n'entre pas en collision avec un réseau existant de l'hôte
      (`docker network inspect` / `ip route`). Sinon, ajuster le subnet dans
      `docker-compose.yml` **et** `TRUSTED_PROXY_IPS`.
- [ ] **Copie hors-site** : planifier la recopie de `BACKUP_HOST_DIR` (défaut
      `./backups`) vers le support hors-site, et **tester une restauration**
      (`scripts/pg_restore_verify.ps1`, verdict `SUCCÈS`).
- [ ] **Coupure électrique** : couper le secteur, vérifier bascule UPS puis
      **arrêt propre**, rallumer, confirmer que `docker compose up -d` (restart
      policy) relance tout et que `qualify_stack.sh` repasse au vert.
- [ ] **Panne PostgreSQL/Redis** : `docker compose stop postgres` puis `start` —
      l'app doit se rétablir sans intervention manuelle.
- [ ] **Automate réel** : brancher un DH36, envoyer des trames, vérifier leur
      archivage (file Redis brute) ; tester déconnexion/reconnexion et reprise
      après coupure — cf. §16.
- [ ] **Certificat racine Caddy** (CA interne) installé sur les postes clients,
      ou certificat public/fourni configuré dans `deploy/Caddyfile`.

**Le serveur est qualifié quand A.3 sort 0 ET toutes les cases A.1/A.4 sont
cochées.** Consigner la date, l'opérateur et le tag d'image (`RUGGYLAB_IMAGE`).

---

## Partie B — Pilote encadré

Objectif : usage réel **sans production de résultats officiels** — on éprouve les
personnes et les procédures, pas seulement la machine.

### B.1 Cadre

- [ ] Périmètre écrit : quels examens, quels postes, quelle durée.
- [ ] **Aucun compte-rendu officiel** émis pendant le pilote (données marquées
      « test/pilote » ; nettoyage via `scripts/cleanup_uat_data.py` en fin).
- [ ] Comptes nominatifs par rôle (technician/officer/accountant) — pas de compte
      partagé ; mot de passe admin changé.
- [ ] Référentiels initialisés (bioref, tarifs ajustés, cibles TAT).

### B.2 Gouvernance de la validation (décision 2026-07-08)

Le laboratoire a décidé que les comptes-rendus sortent **sans validation
biologique obligatoire** (`REQUIRE_VALIDATION_FOR_RELEASE=false`), faute de
biologiste validateur en poste. Pendant le pilote :

- [ ] Les **valeurs critiques** restent acquittées (le système l'impose).
- [ ] Tenir une **file des résultats à re-valider** dès l'arrivée du biologiste.
- [ ] **Basculer `REQUIRE_VALIDATION_FOR_RELEASE=true`** ce jour-là (une variable
      d'environnement + `docker compose up -d`).

### B.3 Mode dégradé (à répéter avant le pilote)

- [ ] Procédure papier connue (registre, numéro temporaire, double contrôle) —
      cf. `docs/LIVRABLES_FORMATION_EXPLOITATION.md` et §29.
- [ ] Simuler panne serveur / LAN / imprimante : l'équipe sait basculer sur
      papier et **ressaisir** ensuite sans doublon (heure réelle ≠ heure de
      saisie).

### B.4 Sortie de pilote

- [ ] `qualify_stack.sh` repassé au vert en fin de pilote.
- [ ] Sauvegarde + **restauration testée** sur instance vierge.
- [ ] Incidents consignés, procédures ajustées.
- [ ] Décision go / no-go pour la production clinique réelle (rappel : elle exige
      aussi le moteur d'interprétation unifié et le versionnement des résultats —
      cf. ARCHITECTURE_AS_BUILT §11).
