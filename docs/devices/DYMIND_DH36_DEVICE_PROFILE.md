# Fiche de commissioning — Dymind DH36

## 1. Identité confirmée

- Fabricant communiqué : Dymind.
- Modèle communiqué : DH36.
- Fonction observée : analyseur d'hématologie à différenciation trois populations.
- Aucun numéro de série complet n'est consigné dans Git.

## 2. Informations inconnues

- plaque et identifiant d'actif contrôlés ;
- firmware installé ;
- configuration de communication active ;
- accessoires, options et révision matérielle ;
- paramètres, codes, unités et flags réellement configurés.

## 3. Documents disponibles

- Identification et fonction consignées dans l'inventaire 2026.
- Checklist RuggyLab générique de commissioning.
- Code historique d'ingestion DH36 et stub générique Dymind, tous deux
  désactivés par défaut.

## 4. Documents manquants

- manuel opérateur applicable au modèle et au firmware ;
- manuel LIS, interface ou communication ;
- table des codes, unités et flags ;
- spécification du framing, de l'encodage, des ACK/NAK, timeouts et retries ;
- preuve de configuration locale et procédure de maintenance.

## 5. Connecteurs observés

Aucun connecteur n'est attribué avec une certitude suffisante au DH36 dans
l'inventaire fourni. Une photographie de port ne doit pas être interprétée comme
preuve de protocole.

## 6. Protocole confirmé ou inconnu

**Inconnu.** Le code HL7 historique ne constitue pas une preuve du protocole de
l'appareil réel.

## 7. Driver RuggyLab

- ingestion DH36 historique : présente mais protégée et désactivée par défaut ;
- listener DH36 : désactivé par défaut ;
- parseur générique Dymind : stub avec protocole inconnu.

Aucun de ces composants n'est qualifié pour cet appareil réel.

## 8. État du registre Equipment

Aucune identité réelle, interface, qualification, preuve, méthode, unité ou
analyte n'a été prérempli par la migration `20260724_0039`. Toute interface
future doit rester `enabled=false` jusqu'au commissioning signé.

## 9. Qualification technique

Non commencée. Elle exige l'identité exacte, le firmware, la spécification
d'interface, un profil versionné et des preuves de framing, ACK/retry,
idempotence et reprise.

## 10. Qualification clinique

Non commencée. Aucun mapping analyte/méthode/unité, intervalle, flag ou contrôle
qualité n'est approuvé.

## 11. Tests synthétiques requis

- trames dérivées de la spécification constructeur, jamais inventées ;
- messages valides, partiels, concaténés, corrompus et hors taille ;
- identifiant, code, unité et flag inconnus ;
- ACK/NAK, timeout, retry, déconnexion et reprise ;
- rejeu séquentiel et concurrent sans double résultat, stock ou audit ;
- panne Redis/PostgreSQL sans écriture médicale partielle.

## 12. Tests réels requis

Après autorisation distincte : identité/firmware, câble et paramètres, corrélation
sur échantillons de qualification non patients, contrôles qualité, déconnexion,
rejeu et suspension. Les critères et l'opérateur doivent être signés avant test.

## 13. Statut final

**DOCUMENTATION MANQUANTE**

L'appareil reste non qualifié, désactivé et non activable en clinique.
