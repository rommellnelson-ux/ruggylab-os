# Fiche de commissioning — Microscope Magnus Epiled Theia-I MLXi

## 1. Identité confirmée

- Désignation communiquée : Magnus Epiled Theia-I MLXi.
- Fonction : microscope utilisé dans un workflow d'observation humaine.
- Aucun numéro de série complet n'est consigné.

## 2. Informations inconnues

- plaque, fabricant légal, révision, identifiant d'actif et configuration ;
- présence et identité d'un dispositif d'imagerie distinct ;
- interface, logiciel, format et chaîne de transfert d'image éventuels ;
- maintenance, qualification optique et paramètres d'acquisition.

## 3. Documents disponibles

- identification communiquée ;
- workflow RuggyLab de réservation/capture d'image et analyse paludisme
  fail-closed ;
- checklist générique de commissioning.

## 4. Documents manquants

- plaque et manuel applicables ;
- inventaire de tout module caméra ou logiciel ;
- preuve de toute interface ou transfert d'image ;
- procédures de maintenance, nettoyage et qualification optique ;
- dossier de validation d'un éventuel modèle ML.

## 5. Connecteurs observés

Aucun connecteur n'est démontré pour ce microscope dans l'inventaire. Une caméra
ou un poste distinct ne doit pas être supposé.

## 6. Protocole confirmé ou inconnu

Aucun protocole appareil n'est confirmé. Le workflow actuel est humain et
supervisé.

## 7. Driver RuggyLab

RuggyLab peut réserver une référence d'image sans association approximative
d'équipement. L'analyse paludisme n'a plus de fallback heuristique et ne modifie
pas `Result`, sa criticité ou sa validation.

## 8. État du registre Equipment

Aucune identité ou interface réelle n'est créée. Un éventuel module d'imagerie
doit être identifié séparément s'il constitue un équipement distinct.

## 9. Qualification technique

Non commencée pour l'imagerie intégrée. L'utilisation optique manuelle exige sa
propre qualification de fonctionnement et de maintenance.

## 10. Qualification clinique

Le résultat repose sur une observation humaine habilitée et une revue distincte.
Aucun modèle ML, jeu de validation ou décision automatisée n'est homologué.

## 11. Tests synthétiques requis

- fichier image de test sans donnée patient ;
- contrôle des chemins, formats, permissions et erreurs ;
- modèle absent/invalide : échec explicite sans mutation clinique ;
- aucune association automatique, criticité ou validation ;
- traçabilité de la sélection et de la revue humaine.

## 12. Tests réels requis

Après autorisation : qualification optique, maintenance, capture supervisée,
reproductibilité du workflow humain et, séparément, validation scientifique de
tout modèle candidat sur un jeu approuvé.

## 13. Statut final

**DOCUMENTATION MANQUANTE**

Le microscope reste utilisable uniquement selon le workflow humain autorisé ;
aucune automatisation clinique n'est activable.
