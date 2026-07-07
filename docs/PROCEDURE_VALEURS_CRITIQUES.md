# Procédure — Valeurs critiques

| Élément | Valeur |
|---|---|
| Objet | Détecter, confirmer, communiquer et tracer une valeur critique |
| Priorité | Immédiate |
| Statut | Projet à valider avec les responsables médicaux |
| Version | 1.0 — juillet 2026 |

## 1. Définitions

Une **valeur critique** est un résultat atteignant ou dépassant un seuil local
nécessitant une action urgente. Les seuils bas et hauts sont inclusifs dans
RuggyLab : une valeur égale au seuil est critique.

Un indicateur simplement bas ou haut n'est pas nécessairement critique.

## 2. Gouvernance des seuils

La direction médicale doit approuver, dater et versionner :

- l'analyte et son unité UCUM ;
- la population concernée (âge, sexe, contexte) ;
- les seuils bas et hauts ;
- les exceptions ;
- le délai et les personnes à prévenir ;
- les règles de confirmation ou répétition.

Les valeurs initiales du logiciel ne remplacent pas cette approbation locale.

## 3. Conduite immédiate du technicien

Lorsqu'une alerte critique apparaît :

1. interrompre la routine et ouvrir le résultat ;
2. confirmer l'identité, la prescription et l'échantillon ;
3. vérifier l'unité, les flags, l'appareil, le contrôle qualité et les
   interférences ;
4. répéter ou confirmer l'analyse si la procédure locale le demande ;
5. prévenir sans délai le professionnel habilité selon la liste d'escalade ;
6. demander une reformulation de la valeur lorsque cette pratique est imposée ;
7. documenter la communication ;
8. seulement ensuite, marquer la valeur comme prise en charge dans RuggyLab.

L'acquittement logiciel ne signifie pas à lui seul que la communication
clinique a effectivement eu lieu.

## 4. Informations à tracer

RuggyLab enregistre actuellement l'utilisateur et l'heure de l'acquittement.
Jusqu'à l'extension du formulaire, le registre critique local doit également
contenir :

- patient, IPP, échantillon et résultat ;
- analyte, valeur, unité et seuil ;
- résultat de la vérification ou répétition ;
- nom et fonction de la personne avertie ;
- service et moyen de communication ;
- heure du premier appel et de la communication réussie ;
- confirmation de lecture/reformulation si applicable ;
- conduite communiquée ou commentaire ;
- tentatives infructueuses et escalade.

## 5. Acquittement dans RuggyLab

L'utilisateur ouvre le résultat critique puis utilise **Prendre en charge**.
Une prise en charge groupée existe dans le cockpit ; elle ne doit être utilisée
que si chaque communication clinique a déjà été effectuée et documentée.

Une valeur critique non acquittée :

- reste visible dans la file prioritaire ;
- bloque la sortie du compte rendu ;
- doit être traitée avant le flux de routine.

## 6. Échec de communication

Si le premier destinataire ne répond pas :

1. consigner l'heure et le moyen utilisé ;
2. suivre la chaîne d'escalade locale ;
3. réessayer aux intervalles prescrits ;
4. ne pas acquitter comme « prise en charge » tant qu'aucune communication
   conforme n'est obtenue ;
5. signaler tout dépassement de délai comme non-conformité si requis.

## 7. Correction d'une valeur critique

Si une erreur est découverte :

- ne jamais écraser silencieusement le résultat ;
- appliquer la procédure d'amendement ;
- prévenir le destinataire d'une correction déjà diffusée ;
- conserver la trace de l'ancienne valeur et de la nouvelle ;
- réévaluer la criticité et recommencer la communication si nécessaire.

## 8. Revue périodique

Le responsable qualité suit au minimum :

- nombre de valeurs critiques ;
- taux et délai d'acquittement ;
- communications hors délai ;
- échecs d'escalade ;
- corrections après communication ;
- adéquation des seuils.

