# Fiche de commissioning — Anbio / BIOSCANN CHEM 100

## 1. Identité confirmée

- Marque visible sur le manuel : BIOSCANN.
- Modèle : CHEM 100.
- Fonction : analyseur d'immunofluorescence.
- Une plaque a été associée à Anbio Biotechnology ; la relation juridique
  fabricant/marque reste à confirmer.

## 2. Informations inconnues

- fabricant légal exact, identifiant d'actif, série expurgée et firmware ;
- configuration, révision matérielle et logiciels installés ;
- rôle des ports, paramètres et format de communication ;
- examens, réactifs, méthodes, unités, flags, calibration et CQ.

## 3. Documents disponibles

- `Operation Manual`, version 1.0, observé sous forme photographiée ;
- identification CHEM 100 et plaque associée à Anbio Biotechnology ;
- inventaire contrôlé des connecteurs visibles.

## 4. Documents manquants

- revue complète et référence contrôlée du manuel ;
- manuel LIS, technique ou communication si distinct ;
- paramètres et brochage RS-232 ;
- rôle du port USB-B et pilote éventuel ;
- format, framing, codes, unités, flags, ACK/NAK et reprise ;
- preuve du firmware et procédures de maintenance/CQ.

## 5. Connecteurs observés

RS-232, USB type B et alimentation DC 12 V. Leur présence ne démontre pas leur
rôle ni un protocole LIS.

## 6. Protocole confirmé ou inconnu

**Inconnu.** Aucun format constructeur de résultat ou contrat ACK/retry n'est
confirmé.

## 7. Driver RuggyLab

`AnbioImmunoParser` est un stub avec `protocol="unknown"` et parsing non
implémenté. La gateway associée est désactivée par défaut.

## 8. État du registre Equipment

Aucune identité, interface, qualification, preuve ou portée analytique réelle
n'est créée. Une future interface doit rester désactivée jusqu'au commissioning.

## 9. Qualification technique

Non commencée. Elle exige identité/firmware, rôle des ports, paramètres,
spécification de message, driver versionné et tests d'erreur/reprise.

## 10. Qualification clinique

Non commencée. Aucun examen, réactif, méthode, unité, flag, calibration ou CQ
n'est approuvé dans le registre.

## 11. Tests synthétiques requis

Messages dérivés du constructeur : valides, invalides, partiels, concaténés,
dupliqués, codes/unités inconnus, ACK/NAK, timeout, déconnexion, panne de
persistance et quarantaine sans écriture clinique.

## 12. Tests réels requis

Après autorisation : rôle RS-232/USB-B, paramètres, corrélation sur matériaux de
contrôle, calibration, CQ, reprise et suspension, avec preuves et opérateurs
signés.

## 13. Statut final

**DOCUMENTATION MANQUANTE**

L'appareil reste non qualifié et non activable en clinique.
