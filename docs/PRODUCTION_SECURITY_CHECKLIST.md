# Checklist sécurité d'infrastructure

Cette checklist complète les contrôles applicatifs. Elle doit être renseignée
sur l'hôte réel avant le go-live.

## Secrets

- injecter les secrets depuis le gestionnaire de secrets ou l'environnement du
  service, avec droits de lecture limités ;
- ne jamais placer `.env`, dumps, certificats privés ou clés de service dans le
  dépôt, les images ou les sauvegardes non chiffrées ;
- utiliser un secret distinct par environnement et documenter propriétaire,
  date de rotation et procédure de révocation ;
- faire tourner immédiatement toute valeur exposée dans un terminal partagé,
  un ticket ou un journal.

Le fichier `.env` reste acceptable pour un poste de développement. Docker
Compose lit aussi directement les variables injectées par le service ou le
shell ; en production, préférer cette voie ou générer un fichier éphémère
protégé (`chmod 600`) puis le supprimer.

## HTTPS

- terminer TLS 1.2/1.3 dans Caddy, Nginx ou Traefik ;
- rediriger HTTP vers HTTPS et automatiser le renouvellement du certificat ;
- transmettre `X-Forwarded-Proto`, `X-Forwarded-For` et `Host` uniquement
  depuis le proxy de confiance ;
- vérifier depuis un autre poste que `5432`, `6379`, `8000`, `9090` et `3000`
  ne sont pas joignables publiquement ;
- n'activer HSTS qu'après validation du domaine et de HTTPS.

## Cloisonnement

La configuration Compose sépare trois réseaux : `frontend`, `database`
(`internal`) et `monitoring`. PostgreSQL et Redis ne publient aucun port.
L'application, Prometheus et Grafana sont liés à la boucle locale.

Le pare-feu de l'hôte doit n'autoriser en entrée que :

- `443/tcp` depuis les réseaux utilisateurs autorisés ;
- `22/tcp` ou RDP depuis le VLAN/VPN d'administration ;
- le port analyseur/DH36 seulement depuis le VLAN des automates, s'il est
  utilisé.

Les sauvegardes hors site doivent utiliser une destination distincte avec
chiffrement, compte dédié, rétention immuable si disponible, et test de
restauration périodique.

## Contrôles externes obligatoires

Ces points ne peuvent pas être prouvés dans le dépôt : règles du pare-feu,
segmentation VLAN, certificat public et renouvellement, droits du gestionnaire
de secrets, livraison Alertmanager, stockage hors site, restauration sur
l'infrastructure cible et procédures d'astreinte.
