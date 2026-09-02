# Runbook — migration du serveur Redis 7.4 vers Valkey

> **Ce document ne promet aucune compatibilité de données.** Il décrit deux
> scénarios distincts, dont un seul est appliqué par la présente PR.

## 0. Ce qui change, en une ligne

Le **serveur** change (Redis 7.4 → Valkey 8.1.9). Le **client** (`redis-py`,
MIT), le **protocole** et le **schéma d'URL** ne changent pas. Le service
Compose s'appelle désormais `valkey`, et le volume `valkey_data`.

## 1. Ce que porte le cache — à lire avant tout

Le service n'est pas un cache d'agrément. Il porte :

| Usage | Conséquence d'une perte |
| --- | --- |
| Cache applicatif | dégradation de performance, pas de perte fonctionnelle |
| Compteurs de rate limiting | fenêtres de limitation réinitialisées |
| Quotas utilisateurs | compteurs remis à zéro |
| Denylist de jetons (JTI révoqués) | **un jeton révoqué redeviendrait accepté jusqu'à son expiration** |
| Fan-out WebSocket / notifications | notifications en vol perdues |
| File de trames automates | **trames non encore consommées perdues** |
| Verrous distribués | verrous relâchés |

Deux lignes appellent une attention particulière : la **denylist de jetons** et
la **file de trames automates**. Les autres se reconstituent d'elles-mêmes.

> Dans la bêta, les interfaces automates sont **désactivées**
> (`ENABLE_DH36_LISTENER=false`, `ANALYZER_RAW_LISTENER_ENABLED=false`) : la
> file de trames est vide par construction.

## 2. Scénario A — bêta, sans données réelles (appliqué ici)

C'est le scénario de la présente PR. Le statut clinique est `REAL_DATA_NO_GO` :
aucune donnée patient réelle ne transite par le service.

1. **Archiver** le volume Redis existant, ne pas le supprimer :
   ```bash
   docker run --rm -v ruggylab_redis_data:/from -v "$PWD":/to alpine \
     tar czf /to/redis_data_$(date +%F).tar.gz -C /from .
   ```
2. **Démarrer Valkey sur un volume neuf.** Le volume s'appelle `valkey_data` :
   il n'existe pas encore, Docker le crée vide. C'est délibéré — réutiliser
   silencieusement le volume Redis reviendrait à affirmer une compatibilité de
   format qui n'a pas été testée.
3. **Ne migrer aucune donnée clinique.** Il n'y en a pas.
4. **Reconstituer** ce qui doit l'être : rien, en pratique. Les compteurs de
   rate limiting, les quotas et les verrous se recréent à la demande. La
   denylist repart vide — voir le point de vigilance ci-dessous.
5. **Vérifier** :
   ```bash
   docker compose ps valkey
   docker compose exec valkey valkey-cli ping
   ```

> **Point de vigilance, à énoncer plutôt qu'à taire.** Repartir d'une denylist
> vide signifie que les jetons révoqués **avant** la bascule redeviennent
> acceptés jusqu'à leur expiration naturelle. Sur un environnement de bêta sans
> utilisateur réel, l'effet est nul. Sur un environnement réellement utilisé, il
> ne l'est pas : voir le scénario B.

## 3. Scénario B — environnement déjà utilisé (non appliqué ici)

À instruire séparément, **avant** toute bascule d'un environnement en service.
Aucune étape n'est automatisée, et aucune bascule automatique n'est prévue.

1. **Sauvegarde** : arrêter les écritures, forcer un `BGSAVE`, copier `dump.rdb`
   et `appendonly.aof` hors du volume.
2. **Export compatible** : Valkey 8 lit les formats RDB et AOF de Redis 7.x,
   mais **cela doit être vérifié sur les données réelles, pas supposé**.
3. **Test de restauration dans Valkey** : monter la sauvegarde dans un volume
   Valkey **de test**, démarrer, et contrôler que le serveur charge sans erreur.
4. **Validation des structures**, une par une :
   | Structure | Contrôle |
   | --- | --- |
   | Clés de denylist JTI | présence, TTL restant cohérent |
   | Compteurs de rate limiting | valeurs et TTL |
   | File de trames automates | longueur `LLEN`, ordre des éléments |
   | Verrous | absence de verrou orphelin |
   | Canaux pub/sub | reprise du fan-out |
5. **Rollback** : conserver l'instance Redis arrêtée mais intacte, et son
   volume, jusqu'à validation complète. Le retour arrière consiste à rebasculer
   `REDIS_URL` et à redémarrer — pas à restaurer une sauvegarde.
6. **Aucune bascule automatique.** Le passage se fait sur décision explicite,
   fenêtre planifiée, service arrêté.

## 4. Tests exécutés par la CI

Le job `Stack Docker production (compose réel)` couvre le démarrage, le
healthcheck, la collecte de métriques, le flux clinique synthétique et la
sauvegarde/restauration PostgreSQL avec Valkey en place. La suite `pytest`
couvre le cache, l'expiration, le rate limiting, les quotas, la denylist, le
fan-out et la file de trames — voir `tests/test_valkey_migration.py` pour le
verrou de non-régression.

## 5. Retour arrière du changement de code

Revenir au commit précédent rétablit `redis:7.4-alpine` et le service `redis`.
Le volume `redis_data` n'ayant pas été supprimé par cette migration, l'ancien
état est retrouvé tel quel.
