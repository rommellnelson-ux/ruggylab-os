# Procédure — Correction et amendement d'un résultat

| Élément | Valeur |
|---|---|
| Objet | Corriger un résultat sans perdre la traçabilité |
| Utilisateurs autorisés | Rôle officer ou admin selon la matrice locale |
| Statut | Projet de procédure à valider localement |
| Version | 1.0 — juillet 2026 |

## 1. Principe

Un résultat erroné ne doit jamais être supprimé ni remplacé silencieusement.
Toute correction doit être justifiée, attribuée, horodatée et reliée à la
version diffusée antérieurement.

## 2. Situations déclenchantes

- erreur de saisie ou d'unité ;
- mauvais rattachement ;
- correction instrumentale confirmée ;
- dilution ou calcul erroné ;
- résultat complémentaire modifiant l'interprétation ;
- erreur découverte après remise du compte rendu.

Une suspicion non confirmée doit d'abord conduire à une investigation, sans
modification précipitée.

## 3. Vérifications avant correction

1. Confirmer le patient, l'échantillon et l'examen.
2. Comparer la donnée source, l'appareil et le résultat enregistré.
3. Évaluer l'impact clinique et la nécessité d'une communication urgente.
4. Identifier les rapports déjà produits et leurs destinataires.
5. Obtenir l'autorisation prévue par la matrice des rôles.

## 4. Correction dans RuggyLab

L'utilisateur habilité :

1. ouvre le résultat ;
2. choisit l'action de correction/amendement ;
3. saisit les nouvelles données ;
4. indique un motif explicite d'au moins cinq caractères ;
5. confirme l'opération.

Le logiciel :

- conserve dans l'audit les données avant/après et le motif ;
- recalcule criticité, delta-check, flags et interprétation ;
- réinitialise l'auto-validation ;
- remet la revue biologique en attente ;
- révoque la signature active lorsqu'elle existe ;
- conserve les snapshots de comptes rendus déjà diffusés.

Le résultat analytique demeure une ligne vivante amendée. L'audit et les
snapshots documentaires apportent l'historique ; il ne faut pas présenter ce
mécanisme comme un registre analytique cryptographiquement immuable.

## 5. Nouvelle version du compte rendu

Après contrôle :

1. produire un nouveau compte rendu ;
2. vérifier son numéro de version et son statut ;
3. vérifier que la version antérieure apparaît comme corrigée ou révoquée ;
4. diffuser la nouvelle version aux mêmes destinataires pertinents ;
5. documenter la notification de la correction.

Un snapshot publié précédemment reste conservé. La nouvelle version référence
la précédente dans la chaîne de remplacement.

## 6. Correction critique

Si l'ancienne ou la nouvelle valeur est critique :

- appliquer immédiatement la procédure des valeurs critiques ;
- prévenir explicitement qu'il s'agit d'une correction ;
- tracer les deux valeurs et l'heure de la nouvelle communication ;
- ne pas considérer l'ancien acquittement comme preuve de communication de la
  valeur corrigée.

## 7. Contrôle et revue

L'officier/biologiste revoit le dossier corrigé, l'impact clinique et la
diffusion. Le responsable qualité analyse périodiquement :

- nombre et motifs d'amendements ;
- corrections après diffusion ;
- délais de notification ;
- secteurs ou appareils concernés ;
- actions correctives nécessaires.

## 8. Interdictions

- supprimer le résultat initial pour masquer l'erreur ;
- utiliser un motif vague tel que « correction » sans explication ;
- modifier une valeur sous le compte d'un collègue ;
- remettre une version corrigée sans informer les destinataires d'une version
  antérieure potentiellement utilisée.

