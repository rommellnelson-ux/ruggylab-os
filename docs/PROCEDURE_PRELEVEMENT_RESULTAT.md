# Procédure opérationnelle — Du prélèvement au résultat

| Élément | Valeur |
|---|---|
| Objet | Décrire le circuit standard d'un examen biologique |
| Utilisateurs | Accueil, préleveurs, techniciens, officier/biologiste |
| Statut | Projet de procédure à valider localement |
| Version | 1.0 — juillet 2026 |

## 1. Conditions préalables

Avant toute activité :

1. ouvrir une session avec son compte nominatif ;
2. vérifier le bon fonctionnement du poste, de l'imprimante et du lecteur de
   codes-barres ;
3. vérifier l'état de l'appareil, la maintenance, les réactifs, la calibration
   et les contrôles qualité selon les procédures du laboratoire ;
4. ne jamais utiliser un compte appartenant à un autre agent.

## 2. Identifier le patient

1. Rechercher d'abord le patient par IPP, nom et autres éléments disponibles.
2. Vérifier au moins deux identifiants selon la politique locale.
3. Si le patient n'existe pas, créer son dossier et contrôler le nom, le sexe,
   la date de naissance, le service et l'IPP.
4. En cas de doublon ou de discordance, suspendre l'opération et appliquer la
   procédure d'identitovigilance.

## 3. Enregistrer la prescription

1. Sélectionner le patient.
2. Choisir dans le catalogue les examens effectivement demandés.
3. Vérifier l'urgence, le prescripteur et le service lorsqu'ils sont requis.
4. Enregistrer la prescription.

La prescription liée pilote l'interface de saisie : les examens encore en
attente, leurs analytes attendus et les appareils compatibles sont proposés au
technicien. En présence de plusieurs prescriptions ouvertes, ne pas supposer
le rattachement : sélectionner explicitement le bon dossier.

## 4. Prélever et étiqueter

1. Confirmer l'identité au contact du patient.
2. Choisir le contenant adapté aux examens.
3. Effectuer le prélèvement selon la procédure technique.
4. Étiqueter immédiatement le contenant sans quitter le patient.
5. Enregistrer le code-barres, le préleveur et la date/heure.

Un tube non identifié ou discordant ne doit pas être analysé.

## 5. Réceptionner et évaluer la conformité

À la réception, contrôler :

- l'identité et le code-barres ;
- le type de contenant et le volume ;
- l'intégrité du tube ;
- le délai et les conditions de transport ;
- l'aspect : conforme, hémolysé, ictérique, lipémique, coagulé ou insuffisant.

Enregistrer la réception et l'aspect. En cas de non-conformité, suspendre le
traitement, documenter la décision et demander un nouveau prélèvement lorsque
la procédure locale l'impose. RuggyLab enregistre l'aspect et peut afficher un
avertissement ; la décision d'acceptation reste humaine.

## 6. Orienter et analyser

1. Ouvrir **Résultats** et scanner/saisir le code-barres.
2. Vérifier le patient et le numéro de laboratoire affichés.
3. Sélectionner l'examen prescrit restant à réaliser.
4. Choisir l'appareil proposé ou la saisie manuelle autorisée.
5. Vérifier que le contrôle qualité est acceptable.
6. Lancer l'analyse ou saisir les valeurs.
7. Contrôler les unités avant l'enregistrement.

Le résultat peut être acquis manuellement ou par une interface d'analyseur
autorisée. Une saisie manuelle doit faire l'objet d'une vigilance renforcée.

## 7. Examiner les contrôles automatiques

Après enregistrement, vérifier :

- les indicateurs normal, bas, haut ou critique ;
- l'intervalle de référence applicable ;
- le delta-check et les antériorités ;
- les alarmes instrumentales ;
- la cohérence entre analytes ;
- les interférences préanalytiques ;
- la cohérence patient–prescription–échantillon–appareil.

L'absence de référence applicable doit être affichée comme telle et ne signifie
pas que la valeur est normale.

## 8. Traiter les exceptions

- **Valeur critique** : appliquer immédiatement
  [la procédure dédiée](PROCEDURE_VALEURS_CRITIQUES.md).
- **Résultat incohérent** : vérifier identité, unité, dilution, tube,
  appareil et contrôle qualité ; répéter selon la procédure locale.
- **Panne ou indisponibilité** : suivre
  [la procédure de fonctionnement dégradé](PROCEDURE_FONCTIONNEMENT_DEGRADE.md).
- **Erreur découverte après enregistrement ou diffusion** : suivre
  [la procédure de correction](PROCEDURE_CORRECTION_AMENDEMENT.md).

## 9. Valider et rendre

Le technicien réalise la vérification opérationnelle du dossier. Dans la
configuration actuelle :

1. le résultat enregistré est marqué valide et placé en revue biologique
   différée ;
2. un compte rendu peut être produit sans revue immédiate si la configuration
   locale autorise la publication ;
3. une valeur critique ne peut pas être publiée avant son acquittement ;
4. le rapport est créé sous forme de snapshot versionné ;
5. le destinataire, le canal et la remise doivent être tracés selon la
   procédure locale.

Le rapport doit être relu avant remise : identité, examens, valeurs, unités,
références, commentaires et statut du document.

## 10. Revue biologique différée et clôture

L'utilisateur habilité consulte la file de revue, en priorité les dossiers
critiques ou anciens. Il peut revoir un résultat seul ou plusieurs résultats en
groupe. Toute anomalie conduit à une correction documentée et à la production
éventuelle d'une nouvelle version du rapport.

La clôture opérationnelle n'efface jamais les données initiales ni les
événements d'audit.

## 11. Enregistrements attendus

- identité et IPP ;
- prescription ;
- code-barres et numéro de laboratoire ;
- prélèvement, réception et aspect ;
- appareil ou mode de saisie ;
- valeurs, unités, flags et contrôles ;
- utilisateur et horodatages ;
- acquittement critique le cas échéant ;
- rapport versionné et événements de diffusion ;
- revue biologique ou amendement ultérieur.

