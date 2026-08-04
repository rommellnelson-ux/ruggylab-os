# Fiche de commissioning — Precix / ProCheck Expert

## 1. Identité confirmée

- Appareil POCT présent selon l'inventaire communiqué.
- Cinq paramètres annoncés commercialement : glycémie, cholestérol total,
  acide urique, lactate et corps cétoniques.
- La dénomination exacte Precix/ProCheck doit encore être rapprochée de la
  plaque.

## 2. Informations inconnues

- fabricant, nom commercial exact, modèle, firmware et identifiant d'actif ;
- méthodes, technologies de bandelettes et versions ;
- unités configurables, plages analytiques et interférences ;
- calibration, contrôle qualité et gestion des lots ;
- type de port USB, pilote, protocole et format.

## 3. Documents disponibles

- documentation commerciale ;
- emballage annonçant une transmission de valeurs par USB ;
- code historique de saisie Precix/POCT, désormais fail-closed.

## 4. Documents manquants

- plaque et notice constructeur applicables ;
- spécifications des bandelettes, lots, calibration et CQ ;
- unités, plages analytiques, limites et interférences ;
- manuel de communication USB, pilote et format d'export ;
- catalogue clinique approuvé et versionné.

## 5. Connecteurs observés

Une transmission USB est annoncée commercialement. Le type du port, son rôle et
le format des données ne sont pas certifiés.

## 6. Protocole confirmé ou inconnu

**Inconnu.** L'annonce USB ne démontre ni un protocole, ni un export exploitable.

## 7. Driver RuggyLab

Les routes historiques POCT/Precix sont présentes mais refusent le flux avant
résultat, seuil, stock et audit de succès tant qu'un profil qualifié n'existe
pas. Aucun driver USB n'est qualifié.

## 8. État du registre Equipment

Aucune identité, qualification, interface, méthode, unité ou référence de
catalogue réelle n'est enregistrée par défaut.

## 9. Qualification technique

Non commencée. Elle exige l'identité exacte, la version, le rôle USB, un profil
versionné et la preuve que les valeurs absentes restent absentes.

## 10. Qualification clinique

Non commencée. Les cinq paramètres annoncés ne constituent pas un catalogue
homologué. Méthodes, unités, lots, plages, CQ et règles de revue doivent être
signés.

## 11. Tests synthétiques requis

- cinq paramètres présents/absents, sans remplissage automatique ;
- unités et codes inconnus refusés ;
- lots, calibration et CQ invalides ;
- résultat non biologiquement validé par défaut ;
- rejeu avec future clé D2 ;
- échec d'audit ou de stock avec rollback complet.

## 12. Tests réels requis

Après autorisation : identification, lots et bandelettes de qualification,
contrôles qualité, répétabilité, corrélation, export USB éventuel et revue
clinique sur données exclusivement synthétiques ou matériaux de contrôle.

## 13. Statut final

**NON IDENTIFIÉ**

Le flux POCT reste fail-closed et l'appareil non activable en clinique.
