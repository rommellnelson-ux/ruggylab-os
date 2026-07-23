# Runbook de rollback et reprise — RuggyLab OS — 2026

## 1. Portée

Ce runbook prépare un retour contrôlé d'une release RuggyLab OS. Il ne doit être
exécuté que sur un environnement explicitement identifié, par des opérateurs
autorisés. Les commandes sont des modèles : les valeurs d'environnement, noms de
base, secrets et identifiants ne doivent jamais être copiés dans le dossier de
preuve.

Principes :

- privilégier un rollback applicatif par image/SHA immuable ;
- privilégier une migration corrective vers l'avant après écriture réelle ;
- ne jamais lancer un downgrade non répété sur copie/restauration ;
- préserver les données, audits, snapshots, outboxes et versions ;
- arrêter avant toute cible ambiguë ;
- ne jamais utiliser le checkout de développement comme release.

## 2. Déclencheurs

| Niveau | Exemple | Action |
|---|---|---|
| R0 | Alerte sans impact, métrique transitoire | Observer et documenter. |
| R1 | Régression fonctionnelle sans écriture erronée | Désactiver le flux/feature et décider rollback applicatif. |
| R2 | Écritures partielles, duplication, RBAC ou critique erronée | Stopper le flux concerné, geler les preuves, cellule d'incident. |
| R3 | Risque de perte/confusion patient ou intégrité DB | Stop clinique, mode dégradé, direction/biologiste/DBA. |

Un rollback n'est pas automatique si des données ont été écrites avec un schéma
ou une sémantique nouvelle.

## 3. Autorités

- Incident commander : ______________________
- Autorité clinique : _______________________
- DBA : ____________________________________
- Exploitation : ____________________________
- Sécurité/qualité : ________________________
- Autorité de changement : __________________

Deux validations sont requises pour toute restauration ou migration. La
direction clinique décide du mode dégradé.

## 4. Préconditions obligatoires

- [ ] Environnement et cible confirmés par deux personnes.
- [ ] SHA actuel, SHA de retour et digest d'image relevés.
- [ ] Heure de début, symptômes et flux touchés consignés.
- [ ] Sauvegarde récente et checksum disponibles.
- [ ] Restauration de cette sauvegarde déjà vérifiée sur base scratch.
- [ ] Outbox, scheduler, gateway et workers inventoriés.
- [ ] Effets externes et transactions en vol identifiés.
- [ ] Procédure papier/mode dégradé activée si nécessaire.
- [ ] Aucune commande ne contient de secret en clair.

## 5. Collecte de preuves non sensibles

Relever sans payload :

- état des conteneurs/processus et healthchecks ;
- SHA/digest, head Alembic et heure NTP ;
- compteurs HTTP, erreurs, files et outbox ;
- nombre de lignes par statut, jamais le contenu clinique ;
- dernière sauvegarde, checksum et rapport de restauration ;
- journaux corrélés par identifiant technique non patient.

Ne pas copier :

- variables d'environnement ;
- jetons, mots de passe, chaînes de connexion ;
- PDF, résultats, noms, IPP ou codes-barres réels ;
- payload FHIR réel.

## 6. Isolement du flux

1. Bloquer uniquement la route, le gateway ou le worker fautif.
2. Maintenir la lecture si elle est sûre.
3. Empêcher un second scheduler/worker de démarrer.
4. Ne pas supprimer les files.
5. Noter les effets externes susceptibles d'avoir réussi sans statut committé.
6. Informer les utilisateurs du mode dégradé.

Pour le worker Windows local de l'incident du 23 juillet, suivre
`INCIDENT_WORKER_PLANIFIE_2026-07-23.md` et ne pas le redémarrer sans
autorisation séparée.

## 7. Rollback applicatif

Le retour applicatif est préféré lorsque le schéma reste compatible.

1. Vérifier que l'image précédente est disponible par digest.
2. Vérifier que son code supporte le head Alembic actuel.
3. Arrêter les nouveaux effets externes.
4. Basculer la référence d'image vers le digest précédent dans le mécanisme de
   déploiement approuvé.
5. Redémarrer les rôles dans l'ordre défini : web, scheduler unique, gateways
   uniques, workers.
6. Exécuter health/readiness et un smoke synthétique.
7. Vérifier qu'aucun singleton n'est dupliqué.
8. Réouvrir progressivement les flux.

Modèle conceptuel, à ne pas exécuter sans dossier de changement :

```text
image courante  : <registre>/<image>@sha256:<digest-courant>
image de retour : <registre>/<image>@sha256:<digest-approuve>
```

Rollback du rollback : conserver la release fautive isolée, ne jamais réutiliser
son tag mutable ; une nouvelle décision est nécessaire pour la réactiver.

## 8. Migrations

### 8.1 Décision

- Si la release précédente lit le schéma actuel : ne pas downgrader.
- Si une colonne additive gêne : corriger vers l'avant.
- Si un downgrade est exigé : le répéter sur restauration scratch du même type,
  mesurer la perte et obtenir l'autorisation DBA/clinique.

### 8.2 Garde-fous

- head attendu de la PR #80 : `20260723_0038` ;
- chaîne linéaire vérifiée ;
- ne jamais utiliser `downgrade base` sur un environnement avec données ;
- ne jamais supprimer une colonne/table porteuse d'historique sans export et
  décision ;
- arrêter en cas de type incompatible, valeur `NULL` inattendue ou contrainte
  non satisfaite.

### 8.3 Preuve

Archiver : révisions avant/après, durée, checksum du dump, rapport de test,
nombre agrégé de lignes et validation fonctionnelle.

## 9. Restauration PostgreSQL

La restauration remplace l'état de la base ; elle est réservée aux incidents de
données et non aux simples régressions applicatives.

1. Sélectionner une sauvegarde et vérifier son SHA-256.
2. Exécuter `scripts/pg_restore_verify.ps1` sur la base scratch allowlistée.
3. Vérifier schéma, head Alembic, comptes techniques, volumes et smoke.
4. Mesurer la fenêtre de données entre sauvegarde et incident.
5. Faire approuver la perte potentielle par l'autorité clinique et la direction.
6. Isoler l'ancienne base sans la supprimer.
7. Restaurer via la procédure DBA approuvée.
8. Rejouer uniquement les événements dont l'idempotence est prouvée.
9. Réconcilier les effets externes et l'outbox.
10. Réouvrir après réception synthétique.

Le script de vérification ne doit jamais viser la base de production ; sa garde
allowlist et le checksum sont obligatoires.

## 10. Outbox, rapports et effets externes

Avant remise en route :

- compter `pending`, `failed`, `processed`, `dead_letter` ;
- identifier uniquement par identifiant technique les effets ambigus ;
- ne pas marquer manuellement `processed` sans preuve destination ;
- ne pas rejouer deux workers ;
- tester un passage unique avec limite faible ;
- conserver snapshots et versions de rapports.

Après rollback applicatif, vérifier que la release précédente comprend le format
des entrées d'outbox créées par la release nouvelle. Sinon, utiliser un worker de
compatibilité qualifié ou suspendre la diffusion.

## 11. Automates, DH36 et TCP brut

- couper l'entrée d'un seul instrument à la fois ;
- conserver les identifiants de message et files locales ;
- déterminer si l'instrument rejoue après absence d'ACK ;
- ne jamais injecter manuellement une trame réelle dans un environnement de test ;
- réconcilier les compteurs instrument/LIS ;
- réouvrir après preuve d'une seule création.

Pour le TCP brut, appliquer la décision D3 avant reprise.

## 12. Sécurité et authentification

En cas de soupçon de compromission :

- désactiver le compte concerné ;
- révoquer les sessions via le mécanisme `auth_version` ;
- faire tourner les secrets dans le gestionnaire prévu, jamais dans Git ;
- préserver les audits ;
- vérifier les rôles et unités ;
- traiter la récupération de compte selon une procédure approuvée.

Ne pas baisser les exigences d'authentification pour accélérer un rollback.

## 13. Contrôles post-reprise

- [ ] Health/readiness verts.
- [ ] Head Alembic conforme.
- [ ] Une seule instance scheduler/gateway/worker.
- [ ] Aucun port technique exposé.
- [ ] Authentification, rôle et unité vérifiés.
- [ ] Patient, échantillon, résultat, critique et rapport synthétiques réussis.
- [ ] Audit atomique présent.
- [ ] Outbox sans croissance anormale ni doublon.
- [ ] Sauvegarde suivante réussie.
- [ ] Alertes et journaux opérationnels.
- [ ] TAT revenu dans la plage approuvée.
- [ ] Utilisateurs informés de la fin du mode dégradé.

## 14. Critères de clôture

- cause racine et chronologie validées ;
- données et effets externes réconciliés ;
- aucun patient réel dans le dossier d'incident ;
- CAPA ouverte si nécessaire ;
- test de non-régression ajouté ;
- runbook mis à jour ;
- décision de réouverture signée.

Verdict : _______________________________________<br>
SHA/digest final : _______________________________<br>
Perte de données : oui / non / inconnue<br>
Effets externes ambigus : oui / non<br>
Signatures : ____________________________________
