# Dossier des décisions P1 — RuggyLab OS — 2026

## Mode d'emploi

Ce dossier prépare huit décisions de gouvernance. Il ne vaut ni approbation
clinique, ni autorisation de migration, ni ordre de déploiement. Les données
historiques n'ont pas été consultées ; toute mention d'inventaire ou de backfill
désigne une opération future sur copie autorisée avant intervention réelle.

Chaque décision doit être signée par le responsable indiqué, datée et reliée à
une PR dédiée. Une case cochée sans identité, date et justification ne clôt pas
le risque.

## Synthèse

| ID | Sujet | Recommandation | Priorité |
|---|---|---|---|
| D1 | Numéros de laboratoire explicites | B si une autorité externe existe, sinon A. | Avant reprise d'historique/pilote. |
| D2 | Idempotence POCT/qualitatif | A, identifiant obligatoire et unique. | Avant connexion réelle. |
| D3 | Durabilité ACK TCP brut | B si les instruments tolèrent mal le retry, sinon A. | Avant listener réel. |
| D4 | Fallback paludisme | A en exploitation. | Bloquant avant toute écriture clinique. |
| D5 | Visibilité MADO | B, unité obligatoire indépendante du patient. | Avant usage multi-unité. |
| D6 | FHIR pharmacie | B, faits persistés comme source. | Avant exposition partenaire. |
| D7 | MFA privilégiée | B pour ADMIN/OFFICER, TOTP transitoire. | Avant production. |
| D8 | Résultats immuables | A, table de versions chaînées. | Avant politique d'amendement définitive. |

## D1 — Numéros de laboratoire explicites

### État actuel et preuve

- `app/schemas/sample.py:SampleBase.lab_number` accepte une chaîne optionnelle.
- `app/models/ruggylab_os.py:Sample.lab_number` est indexé mais non unique.
- `app/api/v1/endpoints/samples.py:create_sample` alloue un numéro sérialisé
  uniquement lorsque le client n'en fournit pas.
- La présence de doublons historiques est inconnue.

### Scénario de risque

Deux clients ou imports fournissent le même numéro. Deux échantillons distincts
peuvent alors être recherchés, imprimés ou rapprochés sous le même identifiant.

### Impacts

- **Clinique :** confusion d'échantillon ou de résultat plausible.
- **Sécurité :** risque indirect de consultation du mauvais dossier.
- **Opérationnel :** rapprochement, étiquetage et investigation difficiles.
- **Historique :** toutes les lignes portant un numéro explicite sont
  potentiellement concernées ; aucun volume n'est connu.
- **Migration :** nécessaire pour une contrainte simple ou composite, après
  inventaire et résolution contrôlée des doublons.

### Options

- **A — Autorité interne unique.** Refuser tout numéro client et utiliser
  l'allocation interne sérialisée.
- **B — Autorités externes nommées.** Ajouter source, namespace, portée
  site/unité/année et contrainte composite ; conserver le numéro interne.
- **C — Maintien libre avec détection applicative.** Conserver le champ actuel et
  alerter sur doublon. Cette option ne protège pas correctement la concurrence
  sans contrainte DB et n'est pas recommandée.

### Recommandation

B si un HIS ou instrument possède une véritable autorité ; sinon A. Ne jamais
écraser silencieusement un numéro historique.

### Coût, complexité et réversibilité

- A : coût moyen, complexité moyenne, réversible côté API mais pas après
  suppression de données — aucune suppression n'est recommandée.
- B : coût élevé, complexité élevée, réversible par lecture des deux identifiants
  pendant une période de transition.
- C : coût faible, protection insuffisante.

### Tests requis

- allocations automatiques concurrentes PostgreSQL ;
- valeurs explicites séquentielles et concurrentes ;
- portée année/site/unité ;
- import et édition ;
- génération/recherche de code-barres ;
- inventaire des doublons sur copie autorisée.

### Déploiement et rollback

Déployer d'abord les nouvelles colonnes nullable et la lecture double, puis
backfill contrôlé, puis contrainte. En rollback, garder les nouvelles colonnes et
revenir à la lecture précédente ; ne jamais supprimer le mapping historique.

### Décision attendue

Autorité du numéro, namespace, portée, traitement des doublons et date de bascule.

- [ ] Option A
- [ ] Option B
- [ ] Option C — dérogation motivée
- [ ] Refus / étude complémentaire

Responsables : direction de laboratoire, biologiste, responsable intégration.
Date et justification : ______________________________

## D2 — Idempotence POCT et qualitatif

### État actuel et preuve

`results_poct.submit_poct_batch` et
`results_qualitative.submit_qualitative_result` créent un nouveau `Result` à
chaque appel. Aucun identifiant d'acquisition unique n'est persisté. La
transaction locale, l'audit, le verrou échantillon et le refus du statut annulé
sont déjà présents.

### Scénario de risque

Un retry HTTP après timeout crée un second résultat et peut provoquer une seconde
consommation. Une déduplication basée uniquement sur l'échantillon supprimerait
à l'inverse une mesure légitime.

### Impacts

- **Clinique :** résultats dupliqués ou mesure légitime ignorée.
- **Sécurité :** faible impact direct ; intégrité et traçabilité dominent.
- **Opérationnel :** stock, statistiques, alertes et corrections.
- **Historique :** doublons éventuels inconnus ; ne pas les fusionner
  automatiquement.
- **Migration :** ajout d'une clé source/identifiant, nullable pour l'historique,
  puis unicité sur les nouvelles acquisitions.

### Options

- **A — `acquisition_id` obligatoire.** Clé unique avec source/namespace.
- **B — Fenêtre temporelle.** Empreinte échantillon/appareil/examen/heure.
- **C — Contrat par source.** Message-control-id automate, run-id POCT et UUID de
  saisie qualitative, normalisés dans une même table d'idempotence.

### Recommandation

A comme contrat API minimal ; C peut être son implémentation multi-source. B
n'est qu'un filet provisoire et peut supprimer une acquisition légitime.

### Coût, complexité et réversibilité

Coût moyen, complexité moyenne à élevée. Réversible par acceptation temporaire
des appels sans clé, mais la contrainte doit rester active pour les sources
basculées.

### Tests requis

- même clé séquentielle et concurrente sur PostgreSQL ;
- même payload avec deux clés distinctes ;
- rollback stock/audit ;
- collision entre sources ;
- durée de rétention et rejeu après redémarrage.

### Déploiement et rollback

Ajouter la clé nullable, publier le contrat client, observer, rendre obligatoire
par source puis ajouter la contrainte. En rollback, conserver les clés écrites
et désactiver seulement l'obligation côté client.

### Décision attendue

Producteur de la clé, format, namespace, durée de vie et réponse HTTP au rejeu.

- [ ] Option A
- [ ] Option B
- [ ] Option C
- [ ] Refus / étude complémentaire

Responsables : intégration, laboratoire, fabricants POCT.<br>
Date et justification : ______________________________

## D3 — Durabilité de l'ACK TCP brut

### État actuel et preuve

`raw_tcp_listener._handle_client` appelle `_store_frame`, puis
`_acknowledge`. Si Redis est indisponible, `_store_frame` utilise un tampon
mémoire borné. Un ACK peut donc précéder toute écriture durable.

### Scénario de risque

Redis est indisponible, la trame est placée en mémoire, un ACK est envoyé puis le
processus s'arrête avant replay. L'instrument ne renvoie pas nécessairement la
trame.

### Impacts

- **Clinique :** résultat d'automate manquant ou retardé.
- **Sécurité :** faible impact direct.
- **Opérationnel :** réconciliation instrument/LIS et intervention manuelle.
- **Historique :** aucune donnée n'est à migrer ; les contrats instrument sont à
  inventorier.
- **Migration :** aucune migration SQL obligatoire ; stockage durable local
  éventuel à qualifier.

### Options

- **A — Pas d'ACK sans Redis.** Laisser l'instrument appliquer son retry.
- **B — Journal local durable.** Écrire et fsync une outbox locale avant ACK,
  puis replay idempotent.
- **C — Politique par instrument.** A ou B selon le contrat ACK/retry, avec
  configuration explicite et défaut fail-closed.

### Recommandation

B si les instruments tolèrent mal les retries réseau ; sinon A. C est adapté à
un parc hétérogène seulement si chaque profil est homologué.

### Coût, complexité et réversibilité

A : faible coût, complexité faible, mais dépend du comportement instrument.<br>
B/C : coût et complexité élevés ; rollback vers A possible en gardant l'outbox
pour finir son replay.

### Tests requis

- Redis coupé avant réception ;
- arrêt brutal après écriture locale et avant ACK ;
- reprise et déduplication ;
- tampon plein ;
- trames partielles ;
- tests avec simulateur puis instrument physique.

### Déploiement et rollback

Piloter un type d'instrument, surveiller ACK/retry et backlog, puis étendre.
Rollback : désactiver les nouvelles connexions, finir le replay durable et
revenir à la politique précédente documentée.

### Décision attendue

Contrat de chaque instrument, support de stockage local autorisé, durabilité
requise et temps maximal d'ACK.

- [ ] Option A
- [ ] Option B
- [ ] Option C
- [ ] Refus / étude fabricant

Responsables : laboratoire, biomédical, réseau, intégration.<br>
Date et justification : ______________________________

## D4 — Fallback paludisme

### État actuel et preuve

L'option A a été implémentée par la PR #107. L'heuristique a été supprimée.
Lorsque le modèle est absent ou que l'inférence échoue, le job échoue
explicitement. Même lorsqu'une inférence est fournie, `process_malaria_job` ne
modifie plus `Result`, sa criticité ou sa validation.

La CI #107 `30056391313` est verte. Les tests ONNX restent dépendants d'un
runtime/modèle optionnel ; l'inférence réelle et le modèle homologué ne sont
donc pas qualifiés cliniquement.

### Scénario de risque

Une régression réintroduit une sortie de démonstration dans le résultat clinique,
ou un modèle non validé est présenté comme une aide clinique.

### Impacts

- **Clinique :** faux résultat ou fausse alerte.
- **Sécurité :** intégrité clinique ; le chemin d'image ne doit pas influencer
  un verdict.
- **Opérationnel :** confusion entre démonstration et dispositif qualifié.
- **Historique :** repérer, sur copie autorisée, toute ligne produite par
  l'ancien fallback avant décision de reprise.
- **Migration :** pas nécessaire pour bloquer ; une séparation démonstration
  peut exiger un nouveau modèle/table.

### Options

- **A — Fail-closed clinique.** Aucune mutation de `Result` si le vrai modèle
  qualifié n'est pas chargé.
- **B — Démonstration séparée.** Stockage non clinique, non libérable, non
  critique, visiblement étiqueté.
- **C — Maintien historique avec validation humaine.** Rejetée : une donnée de
  démonstration ne doit pas entrer dans le cycle clinique.

### Recommandation

Option A retenue et implémentée pour tout profil d'exploitation. Une éventuelle
option B nécessite un stockage séparé et une décision ultérieure.

### Coût, complexité et réversibilité

A : faible coût, faible complexité, facilement réversible après qualification
du modèle. B : coût moyen, complexité moyenne. C : non recommandée.

### Tests requis

- modèle absent : zéro écriture clinique ;
- modèle invalide ou hash incorrect ;
- modèle réel chargé et hash homologué ;
- inférence et prétraitement sur jeu qualifié ;
- séparation stricte démonstration/clinique ;
- tests ONNX et PyTorch dans un job ML dédié.

### Déploiement et rollback

Activer d'abord le blocage fail-closed, puis introduire un modèle par SHA/hash
dans un profil dédié. Rollback : désactiver l'inférence et conserver les preuves
sans convertir les sorties en résultats.

### Décision attendue

Profils autorisés, modèle/homologation, propriétaires, jeu de validation et
traitement des sorties historiques non réelles.

- [ ] Option A
- [ ] Option B — démonstration uniquement
- [ ] Option C — dérogation clinique formelle
- [ ] Refus / suspension de la fonction

Responsables : biologiste, direction, qualité, responsable ML.<br>
Date et justification : ______________________________

## D5 — Visibilité MADO

### État actuel et preuve

`EpiNotification` peut stocker un libellé patient, un quartier et un code-barres
sans `patient_id` ni unité. `epi_notifications.list_notifications` liste alors
globalement les notifications pour tout utilisateur clinique actif.

### Scénario de risque

Un utilisateur d'une unité consulte une notification nominative ou
quasi-identifiante d'une autre unité, impossible à cloisonner faute d'unité
persistée.

### Impacts

- **Clinique :** faible impact direct, mais coordination erronée possible.
- **Sécurité :** confidentialité inter-unité.
- **Opérationnel :** transmission district et recherche de cas.
- **Historique :** lignes sans unité à inventorier sur copie autorisée.
- **Migration :** ajout d'une unité et backfill/règle pour les lignes existantes.

### Options

- **A — Patient obligatoire.** Dériver l'unité du patient.
- **B — Unité obligatoire indépendante.** Autoriser une déclaration anonyme tout
  en conservant le cloisonnement.
- **C — Registre district transversal.** Réserver liste et transmission à un rôle
  spécifique, minimiser les identifiants et auditer chaque lecture.

### Recommandation

B pour conserver les déclarations anonymes. C peut compléter B pour les
responsables district, pas remplacer l'unité.

### Coût, complexité et réversibilité

Coût moyen, complexité moyenne. Réversible en lecture double ; ne pas supprimer
les associations historiques.

### Tests requis

- deux unités, avec/sans patient ;
- utilisateur unitaire, OFFICER, ADMIN et rôle district ;
- export/transmission/audit ;
- données historiques sans unité ;
- minimisation des champs.

### Déploiement et rollback

Ajouter l'unité nullable, écrire systématiquement la nouvelle valeur, backfill
approuvé, activer les filtres puis rendre non-null si choisi. Rollback : garder
la colonne et revenir temporairement à l'ancien affichage restreint.

### Décision attendue

Source de l'unité, visibilité locale/district, cas anonymes et rôle transversal.

- [ ] Option A
- [ ] Option B
- [ ] Option C en complément
- [ ] Refus / étude réglementaire

Responsables : épidémiologie, DPO/sécurité, direction médicale.<br>
Date et justification : ______________________________

## D6 — FHIR pharmacie

### État actuel et preuve

Les endpoints `fhir_pharmacy.create_medication_dispense` et
`create_supply_delivery` sont accessibles à tout utilisateur actif. Les builders
émettent le statut FHIR `completed` à partir d'un payload, sans dispensation,
livraison ou facture persistée comme source.

### Scénario de risque

Un utilisateur produit une ressource FHIR concluant à une opération terminée
alors qu'aucun fait métier validé n'existe dans RuggyLab OS.

### Impacts

- **Clinique :** information thérapeutique trompeuse pour un destinataire.
- **Sécurité :** autorisation trop large et intégrité d'échange.
- **Opérationnel :** réconciliation pharmacie/stock/facturation.
- **Historique :** aucune ressource n'est persistée par ces endpoints ; les logs
  externes éventuels sont hors périmètre.
- **Migration :** requise si une dispensation/livraison persistée n'existe pas
  encore comme source.

### Options

- **A — Projection non conclusive.** Endpoint restreint, statut non final et
  marquage explicite de projection.
- **B — Projection depuis un fait persisté.** Construire la ressource uniquement
  depuis une dispensation/livraison autorisée et auditée.
- **C — Désactivation externe.** Conserver le builder pour tests internes, sans
  route exposée jusqu'à disponibilité du modèle métier.

### Recommandation

B. C est le repli sûr avant disponibilité du modèle. A n'est acceptable que si
le profil FHIR du partenaire autorise précisément cette sémantique.

### Coût, complexité et réversibilité

B : coût élevé, complexité élevée. A/C : faible à moyen. Réversibilité par
feature flag ou retrait de la route externe, sans suppression de faits.

### Tests requis

- matrice RBAC ;
- référence inexistante ;
- source annulée/non validée ;
- statut FHIR ;
- audit et minimisation ;
- validation contre le profil partenaire ;
- idempotence de l'export.

### Déploiement et rollback

Maintenir la route non exposée, qualifier le profil, activer pour un partenaire
pilote. Rollback : couper l'exposition, révoquer les jetons d'intégration et
conserver l'audit.

### Décision attendue

Rôles, source persistée, profil partenaire et événement exact autorisant
`completed`.

- [ ] Option A
- [ ] Option B
- [ ] Option C
- [ ] Refus / étude partenaire

Responsables : pharmacie, interopérabilité, sécurité, partenaire FHIR.<br>
Date et justification : ______________________________

## D7 — MFA des comptes privilégiés

### État actuel et preuve

Les comptes reposent sur mot de passe, rate limiting, JWT versionné et révocation
après changement sensible. L'architecture classe la MFA ADMIN/OFFICER comme
cible ; aucun enrôlement, facteur ou récupération MFA n'est implémenté.

### Scénario de risque

Le mot de passe d'un compte privilégié est compromis. Il suffit à ouvrir une
session jusqu'à détection/révocation.

### Impacts

- **Clinique :** actions privilégiées sur validation, configuration ou audit.
- **Sécurité :** élévation complète selon le rôle.
- **Opérationnel :** enrôlement, perte de facteur, support hors horaires.
- **Historique :** aucun backfill clinique ; état d'enrôlement utilisateur à
  ajouter.
- **Migration :** probablement nécessaire pour les facteurs, compteurs et
  récupération.

### Options

- **A — TOTP.** Codes de récupération hors ligne, rotation et anti-replay.
- **B — WebAuthn/clés matérielles.** Deux clés par compte, TOTP de secours
  transitoire.
- **C — Fournisseur d'identité.** OIDC/SAML avec MFA imposée et comptes de
  secours locaux fortement contrôlés.

### Recommandation

B pour ADMIN/OFFICER, TOTP comme transition. C peut être préférable si une
infrastructure d'identité qualifiée existe.

### Coût, complexité et réversibilité

A : coût moyen, complexité moyenne. B/C : coût et complexité élevés. Rollback
possible par politique temporaire mais jamais par désactivation silencieuse de
la MFA sans procédure d'urgence auditée.

### Tests requis

- enrôlement, deuxième facteur et récupération ;
- anti-replay, dérive d'horloge et révocation ;
- perte de clé ;
- changement mot de passe/activation en concurrence ;
- sessions existantes ;
- comptes break-glass et audit.

### Déploiement et rollback

Enrôler d'abord les administrateurs, période de double facteur, enforcement par
rôle, puis OFFICER. Rollback par procédure break-glass datée, limitée et
révoquée après incident.

### Décision attendue

Technologie, rôles, nombre de facteurs, récupération, break-glass, support et
date d'enforcement.

- [ ] Option A
- [ ] Option B
- [ ] Option C
- [ ] Refus / étude IAM

Responsables : sécurité, exploitation, direction, qualité.<br>
Date et justification : ______________________________

## D8 — Version immuable des résultats

### État actuel et preuve

`results.amend_result` remplace `Result.data_points` en place. L'ancien et le
nouvel état sont consignés dans l'audit ; les rapports signés possèdent des
snapshots versionnés. `audit_events` n'est cependant pas immuable en base et
aucune relation `previous_version_id` ne relie les états analytiques.

### Scénario de risque

Après plusieurs amendements, reconstruire la chaîne analytique dépend d'une
piste d'audit modifiable par un accès SQL privilégié. Un export peut confondre
l'état courant et celui d'un rapport ancien.

### Impacts

- **Clinique :** ambiguïté sur l'état ayant fondé une décision.
- **Sécurité :** intégrité médico-légale et responsabilité.
- **Opérationnel :** rapports, FHIR, requêtes et support.
- **Historique :** tous les résultats amendés sont concernés ; volume inconnu.
- **Migration :** oui, avec règle de construction des versions historiques.

### Options

- **A — Table de versions.** Ligne immuable, `previous_version_id`, pointeur vers
  la version courante.
- **B — Event sourcing.** Journal append-only et reconstruction de l'état.
- **C — Table d'amendements append-only.** Conserver `Result` courant mais
  ajouter une chaîne d'amendements signés et une contrainte d'immutabilité.

### Recommandation

A, plus simple à interroger et qualifier. C peut servir de transition si sa
chaîne est réellement immuable ; B est disproportionné sans besoin plus large.

### Coût, complexité et réversibilité

A/C : coût et complexité élevés. B : très élevés. Réversibilité limitée après
écriture ; prévoir lecture compatible plutôt que suppression des nouvelles
versions.

### Tests requis

- deux amendements séquentiels/concurrents ;
- chaîne complète et interdiction update/delete ;
- rapport signé avant/après ;
- FHIR et historique patient ;
- rollback transactionnel ;
- migration sur copie autorisée.

### Déploiement et rollback

Ajouter le modèle, écrire en double, comparer, basculer les lectures puis rendre
les versions immuables. Rollback : conserver les versions et revenir
temporairement à la lecture du pointeur courant ; ne jamais les supprimer.

### Décision attendue

Granularité, source de vérité, migration, rétention, effet sur rapports/FHIR et
droits SQL.

- [ ] Option A
- [ ] Option B
- [ ] Option C
- [ ] Refus / étude d'architecture

Responsables : biologiste, qualité, architecture, base de données.<br>
Date et justification : ______________________________

## Validation globale

- [ ] Les huit décisions ont un propriétaire et une date.
- [ ] Les décisions cliniques sont signées par l'autorité clinique.
- [ ] Les migrations/backfills seront testés sur copie autorisée.
- [ ] Chaque implémentation aura sa PR, ses tests PostgreSQL et son rollback.
- [ ] Aucun arbitrage n'est considéré comme déployé par le seul fait de signer ce document.

Approbateurs : _______________________________________<br>
Date : ______________________________________________
