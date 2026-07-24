# Matrice d'intégration des équipements — 2026

## Politique commune

Toutes les interfaces sont désactivées par défaut. Un connecteur physique ne
prouve ni le protocole ni la capacité LIS. Le statut « non activable en
clinique » signifie que l'interface n'est pas encore qualifiée ; il ne signifie
pas que l'appareil a échoué à une qualification.

| Appareil | Produit des résultats | Mode | Transmission démontrée | Protocole | Port observé | Composant RuggyLab | Homologation / activation | Risque principal | Tests requis |
|---|---:|---|---|---|---|---|---|---|---|
| Dymind DH36 | Oui | Automatique | Inconnue | Inconnu ; ne pas assimiler au code HL7 historique | Non attribué de façon certifiée | Ingestion DH36 historique ; parseur brut Dymind stub ; désactivés | Non qualifié / non activable en clinique | Parser, unités ou identifiants incompatibles avec l'appareil réel | Manuel, trames synthétiques certifiées, framing, ACK/NAK, mapping, rejeu, panne |
| Dymind Semi-auto Chemistry Analyzer | Oui | Semi-automatique | Inconnue | Inconnu | Non attribué de façon certifiée | `DymindBiochemistryParser`, stub, désactivé | Non qualifié / non activable en clinique | Réutilisation erronée du protocole ou mapping d'hématologie | Identification modèle, manuel communication, méthodes, unités, export, rejeu |
| Appareil de coagulation | Oui | Inconnu | Inconnue | Inconnu | Inconnu | Aucun driver dédié qualifié | Non identifié / non activable en clinique | Confusion avec l'appareil de biochimie | Plaque, manuel, tests et protocole propres |
| Anbio / BIOSCANN CHEM 100 | Oui | Inconnu | Non démontrée | Inconnu | RS-232, USB-B | `AnbioImmunoParser`, stub, désactivé | Non qualifié / non activable en clinique | Déduire un protocole depuis la forme du port | Paramètres série, format, codes, unités, ACK/NAK, rôle USB |
| Precix / ProCheck Expert | Oui | Manuel après qualification ; route actuellement refusée | USB annoncé commercialement, protocole inconnu | Inconnu | USB, type exact non certifié | Routes historiques présentes mais fail-closed ; catalogue historique non accessible au flux clinique | Profil non qualifiable dans le modèle actuel / non activable en clinique | Valeurs, unités, seuils ou validation implicites | Appareil explicitement qualifié, cinq analytes fermés, unités, absence de défauts, non-validation, audit |
| Magnus Epiled Theia-I MLXi | Non ; observation humaine | Manuel / supervisé | Non démontrée | Sans protocole démontré | Non démontré | Réservation d'image sans association automatique d'équipement ; IA paludisme fail-closed | Lecture humaine seulement / aucune activation automatique | Résultat, criticité ou validation produits par l'image | Traçabilité image, habilitation, revue distincte, modèle qualifié séparément |
| ZJZD-III Oscillator | Non | Manuel | Sans objet | Sans objet | Aucun requis | Aucun driver requis | Gestion inventaire/maintenance | Classement erroné comme analyseur | Qualification de fonctionnement et maintenance |
| Centrifugeuse 80-2 | Non | Manuel | Sans objet | Sans objet | Aucun requis | Aucun driver requis | Gestion inventaire/métrologie | Capacité/rotor non rapproché de l'inventaire « 12 places » | Inspection rotor, vitesse, minuterie, sécurité, métrologie |
| Autres équipements manuels | Non | Manuel | Sans objet | Sans objet | Aucun requis | Aucun driver requis | Gestion inventaire/maintenance | Confusion avec un producteur de résultats | Identification, maintenance, métrologie selon équipement |

## État des composants logiciels

| Composant | État vérifié | Usage clinique |
|---|---|---|
| Endpoint `/api/v1/dh36/ingest` | Garde `ENABLE_DH36_INGESTION=false` par défaut | Refus 503 tant que non qualifié |
| Listener DH36 | `ENABLE_DH36_LISTENER=false` par défaut | Désactivé |
| Gateway brut multi-analyseurs | Tous les flags appareil sont `false` par défaut | Aucun port ouvert par défaut |
| Parseurs Dymind hématologie, Dymind biochimie, Anbio immuno | `protocol="unknown"` et `NotImplementedError` | Stubs non qualifiés |
| Routes POCT / Precix | Refus contrôlé avant création de résultat, seuil, stock ou audit de succès | Désactivées jusqu'au registre qualifiable |
| Résultat qualitatif | Créé non validé, non critique, sans clôture implicite de l'échantillon | Revue biologique requise |
| Analyse paludisme | Aucun fallback heuristique ; sortie non clinique sur le job uniquement | Aucun effet sur `Result` |
| Registre Equipment | Identité, interfaces, qualifications, analytes et documents normalisés ; aucune donnée réelle préremplie | Capacité de future homologation uniquement |
| Readiness/activation | Snapshot exact, preuve, périmètre et RBAC contrôlés à chaque usage | Aucun listener ou port démarré |

## Séquence minimale avant activation

Identification exacte → document de communication → profil versionné →
simulateur/trames synthétiques → mapping analytes/unités → tests d'erreur et de
rejeu → homologation clinique → approbation nominative → activation limitée au
site et à l'appareil.

La migration `20260724_0039` ne change aucun statut des appareils listés :
ils restent tous **NON QUALIFIÉS / NON ACTIVABLES EN CLINIQUE**.
