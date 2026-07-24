# Checklist de commissioning et qualification des équipements — 2026

## Identification et autorisation

- [ ] Autorisation écrite de test obtenue ; périmètre, date, site et opérateurs nommés.
- [ ] Appareil, fabricant, modèle, numéro de série masqué et firmware vérifiés.
- [ ] Manuel opérateur et spécification de communication revus.
- [ ] Interface, rôle du port, câble, isolation et paramètres confirmés.
- [ ] Profil RuggyLab versionné, désactivé et lié au seul appareil testé.
- [ ] Simulateur ou environnement de qualification isolé disponible.
- [ ] Uniquement des identifiants, échantillons et messages synthétiques.
- [ ] Sauvegarde, rollback, journalisation et critères d'arrêt définis.

## Fiche de preuve par scénario

| Champ | Valeur |
|---|---|
| Appareil / modèle / firmware | |
| Interface et paramètres | |
| Profil / driver / version de configuration | |
| Précondition | |
| Message ou fichier synthétique | |
| Résultat attendu | |
| Écriture attendue ou interdite | |
| Preuve collectée | |
| Opérateur / relecteur / date | |
| Statut d'homologation | |

## Plan RS-232

- [ ] Brochage et câble confirmés par documentation.
- [ ] Baud rate, data bits, parity, stop bits et flow control confirmés.
- [ ] Framing, encodage, caractères de contrôle et taille maximale testés.
- [ ] Message valide, partiel, tronqué, concaténé et corrompu testés.
- [ ] ACK, NAK, silence, timeout et retry testés selon la spécification.
- [ ] Coupure/reconnexion sans duplication ni écriture partielle.

## Plan USB device et export USB

- [ ] Rôle du port confirmé : device, stockage, impression, maintenance ou autre.
- [ ] Pilote et identifiants USB obtenus du constructeur.
- [ ] Aucun pilote installé sur un poste clinique avant approbation.
- [ ] Montage/export testé sur support de qualification sans données réelles.
- [ ] Format, nommage, encodage, atomicité et détection des fichiers confirmés.
- [ ] Fichier incomplet, déjà lu, dupliqué, modifié et inconnu mis en quarantaine.

## Plan Ethernet / TCP

- [ ] Rôle RJ45, adresse, port, direction et chiffrement confirmés.
- [ ] Listener lié uniquement à l'interface/VLAN de qualification.
- [ ] Aucune écoute sur toutes les interfaces sans décision réseau.
- [ ] Connexion, déconnexion, timeout, backoff et redémarrage gateway testés.
- [ ] Message partiel, plusieurs messages par connexion et taille limite testés.
- [ ] Panne Redis/PostgreSQL : aucune écriture médicale partielle.

## Intégrité fonctionnelle

- [ ] Identifiant inconnu → quarantaine/refus, sans résultat.
- [ ] Échantillon annulé → refus, sans résultat, stock ni succès d'audit.
- [ ] Patient non correspondant → refus et alerte technique expurgée.
- [ ] Code examen ou unité inconnus → refus, jamais de valeur par défaut.
- [ ] Doublon/rejeu → un seul effet métier et preuve d'idempotence.
- [ ] Horodatage, fuseau, ordre des messages et date future testés.
- [ ] Valeur absente reste absente.
- [ ] Aucun seuil critique ou intervalle sans règle approuvée et versionnée.
- [ ] Résultat automate/POCT reste non biologiquement validé par défaut sauf
      workflow distinct explicitement homologué.

## Tests spécifiques

### DH36

- [ ] Manuel et protocole du DH36 réel obtenus.
- [ ] Trames synthétiques dérivées de la spécification, jamais inventées.
- [ ] Codes, unités, flags, contrôles, ACK/NAK et rejeu vérifiés.

### Dymind biochimie et coagulation

- [ ] Deux profils séparés ; aucune réutilisation du parseur DH36.
- [ ] Modèle et distinction physique des appareils confirmés.
- [ ] Méthodes, longueurs d'onde, unités et CQ homologués séparément.

### BIOSCANN CHEM 100

- [ ] Rôle RS-232 et USB-B confirmé.
- [ ] Driver dédié seulement après obtention du format constructeur.

### Precix / ProCheck Expert

- [ ] Profil exact et appareil homologué.
- [ ] Catalogue limité aux cinq paramètres annoncés.
- [ ] Unités, méthodes, plages et CQ confirmés.
- [ ] Aucun remplissage, seuil critique ou validation implicite.
- [ ] USB non activé sans protocole/pilote/format confirmés.

### Microscope et paludisme

- [ ] Capture/sélection → observation humaine → saisie habilitée → revue distincte.
- [ ] Aucun résultat, criticité ou validation automatique depuis une image.
- [ ] Modèle absent ou erreur d'inférence → échec explicite sans mutation de résultat.

## Décision de sortie

- [ ] Toutes les preuves sont datées et relues.
- [ ] Les écarts sont classés et les scénarios cliniques bloquants clos.
- [ ] L'homologation précise appareil, firmware, méthodes, analytes, unités,
      driver et version de configuration.
- [ ] L'activation est explicitement approuvée ; sinon le statut reste
      **NON ACTIVABLE EN CLINIQUE**.
