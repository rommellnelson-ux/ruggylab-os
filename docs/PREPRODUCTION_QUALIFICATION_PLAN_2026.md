# Plan de qualification préproduction — RuggyLab OS — 2026

## 1. Objet et règle d'arrêt

Ce plan décrit la qualification d'un environnement de préproduction
représentatif. Il ne constitue pas une autorisation de déploiement. Aucune
donnée réelle de patient ne doit être utilisée ; les jeux sont synthétiques et
identifiables comme tels.

Arrêt immédiat du lot concerné en cas de :

- secret affiché ou copié ;
- connexion involontaire à la production ;
- donnée réelle détectée ;
- migration destructive ou backfill non approuvé ;
- incohérence clinique ;
- absence de sauvegarde/restauration vérifiée ;
- effet externe non isolé ;
- impossibilité d'attribuer un serveur, un réseau ou une base à la
  préproduction.

## 2. Gouvernance et preuves

| Rôle | Responsabilité |
|---|---|
| Responsable de qualification | Plan, preuves, écarts et verdict. |
| Exploitation | Serveur, réseau, sauvegarde, reprise, journaux. |
| DBA | PostgreSQL, droits, migration, restauration. |
| Sécurité | Segmentation, TLS, secrets, comptes, accès. |
| Biologiste/autorité clinique | Référentiels, critiques, validation, rapports. |
| Biomédical/intégration | Automates, POCT, DH36, ACK/retry. |
| Qualité | Traçabilité, NC/CAPA, critères d'acceptation. |

Chaque preuve doit porter : identifiant de test, date UTC, SHA applicatif, image
par digest, opérateur, environnement, résultat, écart éventuel et lien vers
l'artefact. Les captures et logs doivent exclure secrets et données cliniques
réelles.

## 3. Prérequis de démarrage

- [ ] Les décisions D1 à D8 ont un propriétaire et les décisions bloquantes pour
      le périmètre sont signées.
- [x] Le comportement dangereux de `PR80-CLIN-01` est corrigé techniquement :
      qualitatif non validé/non critique, POCT fail-closed et paludisme sans
      mutation clinique (PR #107, CI verte).
- [ ] L'autorité clinique confirme le workflow cible et toute future règle de
      validation/criticité avant réactivation.
- [ ] Le fallback paludisme est fail-closed pour toute écriture clinique.
- [ ] Le SHA, l'image, les migrations et le dossier documentaire sont gelés.
- [ ] L'environnement est formellement identifié « préproduction ».
- [ ] Les services externes sont simulés ou allowlistés vers des cibles de test.
- [ ] Le plan de rollback est approuvé.
- [ ] Le worker planifié local n'est ni utilisé ni redémarré comme substitut à
      un rôle préproduction qualifié.

## 4. Matrice de qualification

### 4.1 Infrastructure

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| INF-01 | Serveur et inventaire | Relever constructeur, série expurgée, OS, firmware. | Fiche signée. | Conforme à la capacité approuvée. |
| INF-02 | CPU/RAM | Charge synthétique et observation. | Rapport d'utilisation. | Pas de saturation pendant UAT. |
| INF-03 | Disques | Capacité, SMART, IOPS et espace libre. | Rapport disque. | Seuils d'alerte et marge définis. |
| INF-04 | Redondance/RAID | Inspection contrôleur et test d'alerte. | Capture expurgée. | État sain, procédure de remplacement. |
| INF-05 | UPS | Test de bascule et arrêt propre. | Procès-verbal. | Autonomie et arrêt conformes. |
| INF-06 | Température | Mesure et alerte. | Relevé. | Plage constructeur respectée. |
| INF-07 | Sécurité physique | Accès, baie, journal visiteurs. | Checklist signée. | Accès restreint. |
| INF-08 | Horloge/NTP | Comparaison serveur, postes, automates. | Écart maximal mesuré. | Tolérance clinique/exploitation approuvée. |

### 4.2 Réseau

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| NET-01 | VLAN | Vérifier serveurs, postes, automates, management. | Schéma as-built. | Flux minimaux uniquement. |
| NET-02 | Allowlists | Tester sources autorisées et refusées. | Matrice de tests. | Refus par défaut. |
| NET-03 | Ports | Scanner depuis chaque zone autorisée. | Liste des ports. | Seuls 80/443 publiés côté utilisateurs ; ports techniques internes. |
| NET-04 | TLS | Chaîne, nom, dates, protocoles. | Rapport TLS. | Certificat approuvé, aucun downgrade interdit. |
| NET-05 | DNS | Résolution directe/inverse si requise. | Résultats synthétiques. | Noms stables. |
| NET-06 | Internet | Tester mode avec/sans Internet. | Journal de test. | Pas de dépendance non documentée. |
| NET-07 | VPN/bastion | MFA, journalisation, durée de session. | PV sécurité. | Accès nominatif et révocable. |
| NET-08 | Pare-feu | Flux positifs/négatifs. | Export de règles expurgé. | PostgreSQL/Redis non accessibles aux postes. |

### 4.3 PostgreSQL

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| PG-01 | Version | Relevé serveur. | Version signée. | Version supportée et identique à la qualification. |
| PG-02 | Moindre privilège | Tester droits applicatifs/admin/backup. | Matrice de permissions. | Aucun droit superflu. |
| PG-03 | Stockage | Vérifier volume, croissance, WAL, espace. | Rapport capacité. | Alertes avant saturation. |
| PG-04 | Migration | Upgrade 0039, downgrade base, upgrade head sur base jetable. | Logs et checksum schéma. | Chaîne linéaire, aucune erreur. |
| PG-05 | Sauvegarde | Produire dump et SHA-256. | Dump de test + manifeste. | Succès et rétention conforme. |
| PG-06 | Restauration | `pg_restore_verify.ps1` sur base scratch allowlistée. | Rapport `SUCCÈS`. | Huit contrôles conformes. |
| PG-07 | Rétention | Simuler rotation. | Inventaire avant/après. | Aucun dump requis supprimé. |
| PG-08 | Chiffrement | Vérifier au repos/transit selon politique. | PV sécurité. | Politique approuvée. |
| PG-09 | Hors site | Copier un dump synthétique chiffré. | Reçu et restauration. | Copie récupérable. |
| PG-10 | PRA | Mesurer RPO/RTO. | Chronométrage. | Objectifs signés. |

### 4.4 Redis et ingestion

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| RED-01 | Version/configuration | Relevé sans secret. | Fiche. | Version supportée. |
| RED-02 | Persistance | Vérifier politique RDB/AOF choisie. | Config expurgée + test. | Conforme au contrat de durabilité. |
| RED-03 | Mémoire/éviction | Injecter charge synthétique. | Courbes. | Pas d'éviction silencieuse de flux clinique. |
| RED-04 | Panne/reprise | Interrompre uniquement la préproduction. | Chronologie. | Reprise déterministe et alertée. |
| RED-05 | ACK TCP | Exécuter le scénario D3 retenu. | Trace instrument/simulateur. | Aucun ACK avant durabilité requise. |
| RED-06 | Rejeu | Redémarrer après file synthétique. | Comptages et clés. | Une seule persistance clinique. |

### 4.5 Application et rôles de processus

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| APP-01 | Image immuable | Vérifier digest et provenance CI. | Digest/attestation. | Aucun `latest`. |
| APP-02 | Secrets | Contrôle de présence sans afficher les valeurs. | Checklist. | Valeurs non-démo et permissions minimales. |
| APP-03 | Migrations | Service run-once puis vérification readiness. | Log expurgé. | Head 0039. |
| APP-04 | Web | Health, readiness, TLS et routes. | Rapport. | Vert. |
| APP-05 | Scheduler | Une instance, fonctions attendues. | Processus/métriques. | Pas de singleton dupliqué. |
| APP-06 | Gateway | Une instance par port/instrument. | Matrice. | Idempotence et authentification conformes. |
| APP-07 | Outbox | File synthétique, retry, dead-letter. | Compteurs. | Aucun doublon, alerte sur âge. |
| APP-08 | Journaux | Échecs synthétiques. | Extraits expurgés. | Pas de secret/payload patient. |
| APP-09 | Métriques | Routes dynamiques et erreurs. | Export Prometheus. | Labels par gabarit, cardinalité bornée. |
| APP-10 | Ports | Vérifier compose de production seul. | `compose ps` et scan. | Aucun port technique publié. |

### 4.6 Postes et périphériques

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| DEV-01 | Imprimantes | Imprimer étiquette/rapport synthétique. | Exemplaire barré TEST. | Lisible et bon format. |
| DEV-02 | Codes-barres | Générer, imprimer, rescanner. | Journal synthétique. | Zéro substitution. |
| DEV-03 | Scanners | Tester formats et erreurs. | Matrice. | Entrée exacte. |
| DEV-04 | Microscope Magnus Epiled Theia-I MLXi | Image synthétique, observation humaine et permissions ; aucun résultat automatique. | Fichier test + PV. | Aucun chemin arbitraire, résultat, criticité ou validation automatique. |
| DEV-05 | Dymind DH36 | Manuel puis simulateur/trames synthétiques ; appareil réel seulement après autorisation. | PV biomédical. | Protocole, mapping, unités, ACK/retry et idempotence approuvés. |
| DEV-06 | Navigateurs | Versions supportées. | Matrice. | Flux critiques utilisables. |
| DEV-07 | Affichage/clavier | Résolution, accents, pavé numérique. | Checklist utilisateur. | Aucune ambiguïté de saisie. |
| DEV-08 | Dymind biochimie semi-auto | Identifier le modèle ; tests propres au manuel de communication. | Profil + PV. | Aucun parseur/mapping DH36 réutilisé. |
| DEV-09 | Appareil de coagulation | Identifier plaque, marque, modèle et manuel avant test. | Fiche d'identité. | Appareil distinct tant qu'aucune preuve de combinaison. |
| DEV-10 | Anbio / BIOSCANN CHEM 100 | Confirmer rôle RS-232/USB-B puis simulateur. | Profil + PV. | Driver dédié, protocole et unités confirmés. |
| DEV-11 | Precix / ProCheck Expert | Profil exact, cinq analytes fermés et saisie synthétique supervisée. | Homologation méthode/appareil. | Non validé par défaut, aucune valeur/seuil/unité fabriqués. |
| DEV-12 | ZJZD-III et centrifugeuse 80-2 | Qualification de fonctionnement, maintenance et métrologie. | Fiches équipement. | Aucun driver ni flux de résultat. |

### 4.7 Utilisateurs et sécurité

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| USR-01 | Comptes nominatifs | Revue sans exporter les identifiants. | PV. | Aucun compte partagé hors break-glass. |
| USR-02 | Rôles | ADMIN/OFFICER/technicien/comptable. | Matrice RBAC. | Moindre privilège. |
| USR-03 | Unités | Deux unités synthétiques. | Matrice accès/refus. | Cloisonnement conforme. |
| USR-04 | Mot de passe | Politique, changement, révocation. | Tests. | Anciennes sessions invalidées. |
| USR-05 | MFA | Exécuter D7 si retenue. | PV enrôlement/reprise. | Comptes privilégiés couverts avant production. |
| USR-06 | Formation | Exercices par rôle. | Feuilles de présence et résultats. | Seuil de réussite approuvé. |
| USR-07 | Support | Astreinte, escalade, délais. | RACI. | Contact disponible pendant pilote. |

### 4.8 Qualification clinique

| ID | Contrôle | Méthode | Preuve attendue | Critère |
|---|---|---|---|---|
| CLN-01 | Référentiels | Revue versionnée par biologiste. | Signature. | Source/date/propriétaire connus. |
| CLN-02 | Valeurs critiques | Matrice synthétique sous/sur seuil. | PV clinique. | Alertes attendues uniquement. |
| CLN-03 | Intervalles/unités | Sexe/âge/unité/méthode. | Matrice. | Aucun mélange de méthode. |
| CLN-04 | Auto-validation | Couverture complète/incomplète. | Tests §5.8. | Abstention en cas de doute. |
| CLN-05 | Validation biologique | Avec et sans exigence de validation. | Décision signée. | Mode provisoire explicitement gouverné. |
| CLN-06 | Critiques | Acquittement, délai, escalade. | Exercice. | Traçabilité complète. |
| CLN-07 | Rapports | Signature, version, correction. | PDF synthétiques. | Snapshot et outbox cohérents. |
| CLN-08 | Qualitatif | Catégorie/organisme/criticité/validateur. | Matrice signée. | Non validé et non critique sans règle approuvée. |
| CLN-09 | POCT | Appareil, méthode, analyte, unité. | Homologation. | Refus tant que le profil précis n'est pas qualifiable. |
| CLN-10 | Paludisme | Modèle absent/réel. | Rapport ML/clinique. | Échec explicite sans modèle ; aucune mutation de résultat même avec inférence. |

## 5. Tests de réception bout en bout

Chaque scénario utilise des identifiants et contenus manifestement synthétiques.

1. **Patient :** création, recherche, deux unités, refus hors périmètre.
2. **Prescription :** même patient que l'échantillon, course concurrente.
3. **Échantillon :** collecte, réception, annulation terminale, code-barres.
4. **Résultat :** manuel, automate, idempotence, stock et audit.
5. **Critique :** détection, notification, acquittement et rapport.
6. **Rapport :** signature, snapshot, outbox, retry et amendement.
7. **Facture/BNPL :** paiement concurrent, annulation selon décision métier.
8. **POCT :** appareil homologué, rejeu et clé d'acquisition.
9. **Qualitatif :** négatif/positif, rôle, unité, criticité approuvée.
10. **DH36/automate :** HMAC, déduplication et stock.
11. **Panne réseau :** retry client, aucune écriture partielle.
12. **Panne Redis :** scénario ACK durable.
13. **Panne PostgreSQL :** rollback et reprise.
14. **Restauration :** dump, checksum, base scratch, smoke.
15. **Impression :** étiquette et rapport marqués TEST.
16. **Rollback :** application, migration compatible et file d'outbox.

## 6. Critères de sortie

La qualification est recevable seulement si :

- toutes les preuves obligatoires sont présentes ;
- aucun P0 n'est ouvert ;
- chaque P1 a une décision ou un contrôle compensatoire daté ;
- les tests PostgreSQL concurrents s'exécutent dans leur job dédié ;
- les skips ML non couverts sont classés et D4 est appliquée ;
- sauvegarde et restauration scratch sont réussies ;
- le rollback est répété ;
- l'autorité clinique signe CLN-01 à CLN-10 ;
- l'exploitation signe les rôles web/scheduler/gateway/outbox ;
- le comité Go/No-Go approuve explicitement le pilote.

## 7. Livrables

- rapport de CI avec SHA ;
- inventaire des skips ;
- matrice de tests et preuves ;
- rapport de restauration ;
- schéma réseau as-built ;
- registre des écarts/NC/CAPA ;
- décisions D1 à D8 ;
- décision PR80-CLIN-01 ;
- inventaire de connectivité, matrice d'intégration, registre des manuels et
  checklist de commissioning des appareils ;
- décision Equipment B/RBAC consignée ; commissioning signé appareil par appareil ;
- checklist d'acceptation opérationnelle ;
- runbook rollback/recovery ;
- procès-verbal Go/No-Go.
