#!/usr/bin/env bash
# Qualification de la stack de production RuggyLab OS sur le serveur cible.
#
# Miroir du job CI `docker-stack`, mais exécuté sur LE serveur du laboratoire :
# c'est la preuve que « ça marche en CI » vaut aussi « ça marche sur ta machine ».
# À lancer APRÈS `docker compose up -d` (fichier de production seul).
#
# Usage :   RUGGYLAB_DOMAIN=labo.exemple.ci ./scripts/qualify_stack.sh
# Sortie 0 = qualifié ; 1 = au moins un contrôle a échoué.

set -uo pipefail

DOMAIN="${RUGGYLAB_DOMAIN:-localhost}"
FAIL=0
pass() { printf '  [OK]   %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; FAIL=1; }
step() { printf '\n== %s ==\n' "$1"; }

echo "Qualification RuggyLab OS — domaine: $DOMAIN — $(date -u +%Y-%m-%dT%H:%M:%SZ)"

step "1. Services démarrés et sains"
for svc in proxy app scheduler analyzer-gateway postgres redis prometheus grafana db-backup; do
  cid=$(docker compose ps -q "$svc" 2>/dev/null)
  if [ -z "$cid" ]; then fail "$svc absent"; continue; fi
  status=$(docker inspect -f '{{.State.Status}}' "$cid")
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$cid")
  if [ "$status" = "running" ] && { [ "$health" = "healthy" ] || [ "$health" = "n/a" ]; }; then
    pass "$svc ($status/$health)"
  else
    fail "$svc ($status/$health)"
  fi
done

step "2. Seul le proxy publie des ports (aucune fuite technique)"
leaked=$(docker compose ps --format '{{.Service}}\t{{.Ports}}' | grep -- '->' | grep -v '^proxy' || true)
if [ -z "$leaked" ]; then pass "seuls 80/443 (proxy) publiés"; else fail "ports publiés hors proxy :"; echo "$leaked"; fi

step "3. Accès applicatif via TLS uniquement"
code=$(curl -sk -o /dev/null -w '%{http_code}' "https://$DOMAIN/api/v1/health" || echo 000)
[ "$code" = "200" ] && pass "https://$DOMAIN/api/v1/health -> 200" || fail "health via TLS -> $code"

step "4. Chemins techniques bloqués au proxy (§14)"
for p in /metrics /docs /openapi.json /redoc; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' "https://$DOMAIN$p" || echo 000)
  [ "$code" = "404" ] && pass "$p -> 404" || fail "$p -> $code (attendu 404)"
done

step "5. Schéma à jour (verrou de migration)"
if docker compose exec -T app python -c "
from app.db.migration_guard import assert_migrations_up_to_date
from app.db.session import engine
assert_migrations_up_to_date(engine)
" 2>/dev/null; then pass "head Alembic = head embarqué"; else fail "schéma non migré (lancer le service migrate)"; fi

step "6. Sauvegarde automatisée fraîche"
if docker compose exec -T db-backup sh -c '
  f=$(ls -t /backups/ruggylab_pg-*.dump 2>/dev/null | head -1) && [ -n "$f" ] &&
  sha256sum -c "$f.sha256" >/dev/null 2>&1' 2>/dev/null; then
  pass "dernier dump présent et intègre (sha256 OK)"
else
  fail "aucun dump vérifié (attendre le 1er cycle db-backup ou vérifier PGPASSWORD)"
fi

step "7. Flux clinique bout-en-bout à travers le proxy"
if docker compose exec -T -e UAT_BASE_URL="https://$DOMAIN" -e UAT_INSECURE_TLS=1 app \
   python -m scripts.uat_smoke >/tmp/qualify_uat.log 2>&1; then
  pass "uat_smoke 15/15 via TLS"
else
  fail "flux clinique KO (voir la sortie ci-dessous)"; tail -5 /tmp/qualify_uat.log 2>/dev/null || true
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RÉSULTAT : QUALIFIÉ (tous les contrôles logiciels passent sur ce serveur)."
  echo "Rappel : les contrôles matériels (UPS, VLAN automates, imprimantes,"
  echo "copie hors-site, coupure/reprise) sont à valider séparément — voir"
  echo "docs/QUALIFICATION_SERVEUR.md."
else
  echo "RÉSULTAT : NON QUALIFIÉ — corriger les [FAIL] ci-dessus avant le pilote."
fi
exit "$FAIL"
