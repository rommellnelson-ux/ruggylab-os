# Checklist d'acceptation opérationnelle — RuggyLab OS — 2026

Cette checklist est remplie sur préproduction avec données synthétiques. Chaque
case exige une preuve référencée, un opérateur et une date. Elle n'autorise ni
la fusion dans `main`, ni le déploiement, ni le redémarrage d'un worker local.

## Identification

- Environnement : ______________________________
- SHA Git : ___________________________________
- Digest image : _______________________________
- Head Alembic attendu : `20260723_0038`
- Date UTC : __________________________________
- Responsable qualification : _________________

## Infrastructure

- [ ] Serveur, CPU, RAM et stockage conformes à la fiche approuvée.
- [ ] Espace libre et seuils d'alerte documentés.
- [ ] RAID/redondance sain et alerte testée.
- [ ] UPS serveur et postes critiques testé avec arrêt propre.
- [ ] Température et sécurité physique conformes.
- [ ] NTP vérifié entre serveur, postes et automates.

Preuves : ______________________________________

## Réseau et sécurité périmétrique

- [ ] VLAN serveurs, postes, automates et management séparés.
- [ ] Allowlists instruments testées positivement et négativement.
- [ ] Seuls 80/443 sont publiés vers les postes utilisateurs.
- [ ] PostgreSQL, Redis, application directe et supervision non exposés.
- [ ] TLS, certificat, DNS et redirection HTTP→HTTPS conformes.
- [ ] VPN/bastion nominatif, journalisé et protégé par MFA.
- [ ] Fonctionnement sans Internet vérifié si requis.
- [ ] Export des règles pare-feu expurgé archivé.

Preuves : ______________________________________

## PostgreSQL

- [ ] Version supportée et stockage persistant.
- [ ] Compte applicatif au moindre privilège.
- [ ] `upgrade head` réussi jusqu'à `20260723_0038`.
- [ ] `downgrade base` puis nouvel `upgrade head` réussis sur base jetable.
- [ ] Chaîne Alembic linéaire, sans head concurrent.
- [ ] Sauvegarde de test produite avec SHA-256.
- [ ] Restauration `SUCCÈS` sur base scratch allowlistée.
- [ ] Rétention, chiffrement et copie hors site testés.
- [ ] RPO/RTO mesurés et acceptés.

Preuves : ______________________________________

## Redis et ingestion

- [ ] Version, mémoire et politique d'éviction documentées.
- [ ] Persistance conforme au contrat retenu.
- [ ] Panne et reprise testées.
- [ ] Décision D3 appliquée : aucun ACK prématuré.
- [ ] Rejeu idempotent vérifié.
- [ ] Backlog et âge de file supervisés.

Preuves : ______________________________________

## Application et déploiement

- [ ] Image référencée par digest/SHA, jamais `latest`.
- [ ] Présence et permissions des secrets vérifiées sans afficher les valeurs.
- [ ] Aucun secret de démonstration.
- [ ] Service migration run-once séparé.
- [ ] Health/readiness verts derrière TLS.
- [ ] Rôles `web`, `scheduler` et `gateway` uniques.
- [ ] Aucun rôle `all` dupliquant les singletons.
- [ ] Logs structurés sans secret, payload patient ni chemin sensible.
- [ ] Métriques par gabarit de route, cardinalité bornée.
- [ ] Alertes sur erreurs, outbox, backup, espace et délais.

Preuves : ______________________________________

## Worker de diffusion et outbox

- [ ] L'incident `INCIDENT_WORKER_PLANIFIE_2026-07-23.md` est traité séparément.
- [ ] Le worker préproduction pointe vers le SHA qualifié.
- [ ] La CLI et l'action planifiée sont compatibles.
- [ ] Une seule instance est active.
- [ ] Passage unique supervisé réussi avant récurrence.
- [ ] Retry et dead-letter testés sans effet externe réel.
- [ ] Aucun doublon de diffusion sur jeu synthétique.
- [ ] Compteurs et plus ancienne entrée sont observables.

Preuves : ______________________________________

## Postes et périphériques

- [ ] Navigateurs et résolutions supportés.
- [ ] Accents, clavier et pavé numérique vérifiés.
- [ ] Imprimante d'étiquettes et imprimante de rapports testées.
- [ ] Codes-barres imprimés puis rescannés sans substitution.
- [ ] Scanner et microscope testés avec contenus synthétiques.
- [ ] Chaque automate/convertisseur est sur UPS si requis.
- [ ] Chaque appareil réel possède une fiche d'homologation et une allowlist.

Preuves : ______________________________________

## Comptes, rôles et unités

- [ ] Comptes nominatifs uniquement ; break-glass séparé et contrôlé.
- [ ] ADMIN, OFFICER, technicien et comptable testés.
- [ ] Deux unités synthétiques prouvent les accès et refus.
- [ ] Le comptable est refusé avant tout effet clinique.
- [ ] Les anciennes sessions sont invalidées après changement sensible.
- [ ] MFA privilégiée appliquée selon D7 avant production.
- [ ] Procédure de récupération de compte approuvée ou escaladée.
- [ ] Formation et support pilote planifiés.

Preuves : ______________________________________

## Qualification clinique

- [ ] Référentiels, unités et intervalles signés par l'autorité clinique.
- [ ] Seuils critiques et procédures d'acquittement signés.
- [ ] Couverture complète exigée pour l'auto-validation.
- [ ] Le mode provisoire sans biologiste est explicitement accepté, limité et daté.
- [ ] La libération avec/sans validation suit la décision de gouvernance.
- [ ] Rapports, corrections et historique sont compréhensibles.
- [ ] La règle qualitative positif→critique et `is_validated` est approuvée ou corrigée.
- [ ] Le catalogue POCT est homologué par appareil/méthode.
- [ ] Le fallback paludisme n'écrit aucune donnée clinique en exploitation.
- [ ] D1 à D8 sont signées ou hors périmètre avec contrôle compensatoire.

Preuves : ______________________________________

## Réception métier synthétique

- [ ] Patient.
- [ ] Prescription/demande biologique.
- [ ] Échantillon, collecte, réception et annulation terminale.
- [ ] Résultat manuel.
- [ ] Résultat critique et acquittement.
- [ ] Rapport signé, snapshot et diffusion.
- [ ] Amendement et nouvelle version de rapport.
- [ ] Facture, paiement et BNPL concurrent.
- [ ] POCT et rejeu.
- [ ] Résultat qualitatif et rejeu.
- [ ] DH36/automate et rejeu.
- [ ] Non-conformité et CAPA concurrentes.
- [ ] FHIR résultat audité.
- [ ] FHIR pharmacie conforme à D6 ou désactivé.
- [ ] TAT et rapports cloisonnés par unité.

Preuves : ______________________________________

## Résilience et reprise

- [ ] Panne réseau contrôlée.
- [ ] Panne Redis contrôlée.
- [ ] Panne PostgreSQL contrôlée.
- [ ] Perte d'un processus web contrôlée.
- [ ] Redémarrage scheduler/gateway sans duplication.
- [ ] Restauration sur base scratch.
- [ ] Rollback applicatif par SHA.
- [ ] Traitement de l'outbox avant/après rollback.
- [ ] Procédure papier/mode dégradé répétée.

Preuves : ______________________________________

## CI et skips

- [ ] Ruff lint et format.
- [ ] mypy.
- [ ] Bandit.
- [ ] Suite complète : 1 308 tests attendus sur le head qualifié.
- [ ] Onze tests PostgreSQL exécutés dans le job PostgreSQL.
- [ ] Upgrade/downgrade/upgrade Alembic.
- [ ] Smoke et UAT PostgreSQL.
- [ ] Docker de production, TLS, ports, backup et rôles.
- [ ] CodeQL.
- [ ] Playwright Node 24.
- [ ] Build d'image.
- [ ] Les trois tests ONNX et le module PyTorch sont couverts par un job ML ou
      explicitement bloqués par D4.
- [ ] `pip-audit` ne signale plus Pillow 12.2.0.
- [ ] Scan de secrets vert.

Run CI / SHA : __________________________________

## Écarts et décision

| Écart | Criticité | Responsable | Échéance | Contrôle compensatoire |
|---|---|---|---|---|
|  |  |  |  |  |
|  |  |  |  |  |
|  |  |  |  |  |

- [ ] Accepté pour pilote.
- [ ] Accepté pour production.
- [ ] Accepté avec conditions listées.
- [ ] Refusé.

Décision : ______________________________________<br>
Autorité clinique : _____________________________<br>
Exploitation : __________________________________<br>
Sécurité/qualité : ______________________________<br>
Date : _________________________________________
