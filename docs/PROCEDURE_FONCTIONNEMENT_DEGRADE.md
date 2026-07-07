# Procédure — Fonctionnement dégradé et reprise

| Élément | Valeur |
|---|---|
| Objet | Maintenir un service sûr lors d'une indisponibilité |
| Déclenchement | Application, réseau, base, appareil, électricité ou impression indisponible |
| Statut | Canevas à adapter et tester localement |
| Version | 1.0 — juillet 2026 |

## 1. Principes

La continuité d'activité ne doit jamais diminuer l'identitovigilance. Le mode
dégradé est déclaré par un responsable identifié, limité dans le temps et suivi
d'une réconciliation complète.

Cette procédure est un canevas : RuggyLab ne fournit pas actuellement un mode
hors ligne multi-postes autonome. Les supports papier, numéros temporaires,
contacts d'escalade et responsabilités doivent être définis localement.

## 2. Déclarer l'incident

1. Noter la date/heure, le poste, l'utilisateur et les symptômes.
2. Vérifier si l'incident est local ou général sans effectuer de manipulation
   destructive.
3. Informer le responsable et le support.
4. Déclarer le passage en mode dégradé.
5. Définir le périmètre : accueil, prélèvement, analyseur, réseau, impression
   ou diffusion.

Ne pas modifier directement la base, désactiver la sécurité ou restaurer une
sauvegarde sans autorisation.

## 3. Enregistrement papier temporaire

Utiliser les formulaires approuvés comportant au minimum :

- numéro temporaire unique ;
- deux identifiants patient ;
- prescription et degré d'urgence ;
- code du tube et type d'échantillon ;
- date/heure de prélèvement et de réception ;
- préleveur et technicien ;
- appareil, résultat, unité, flags et contrôles ;
- communication critique ;
- destinataire et remise du résultat.

Tenir un registre séquentiel des numéros temporaires et empêcher les doublons.

## 4. Traitement selon la panne

### Application ou base indisponible

- utiliser le registre papier approuvé ;
- conserver les tubes et documents dans l'ordre ;
- prioriser urgences et valeurs critiques ;
- ne pas créer plusieurs identifiants pour le même patient ;
- différer les tâches non urgentes.

### Réseau local indisponible

- ne pas déplacer de données nominatives sur une messagerie personnelle ou une
  clé non autorisée ;
- utiliser le poste ou circuit de secours validé ;
- consigner tout échange manuel.

### Analyseur indisponible

- arrêter l'envoi vers l'appareil concerné ;
- appliquer la maintenance de premier niveau autorisée ;
- utiliser un appareil de secours validé ou orienter l'échantillon vers un
  laboratoire partenaire ;
- tracer l'appareil, la méthode et le transfert.

### Imprimante indisponible

- conserver le compte rendu dans la file autorisée ;
- utiliser une imprimante de secours sécurisée ;
- si une transmission urgente est nécessaire, vérifier oralement l'identité du
  destinataire et tracer l'échange.

### Électricité indisponible

- sécuriser appareils, réactifs et échantillons ;
- suivre les durées d'autonomie et températures ;
- arrêter les analyses dans les conditions prévues par les fabricants ;
- documenter toute rupture susceptible d'affecter les résultats.

## 5. Valeurs critiques pendant l'incident

Le circuit critique reste obligatoire :

1. confirmer le résultat ;
2. joindre le professionnel habilité ;
3. tracer sur le registre papier toutes les informations de communication ;
4. faire signer ou contresigner selon la procédure locale ;
5. ressaisir et réconcilier l'événement au rétablissement.

## 6. Rétablissement et réconciliation

Après autorisation de reprise :

1. vérifier la santé de l'application et l'accès aux données ;
2. annoncer officiellement la fin du mode dégradé ;
3. désigner les agents chargés de la ressaisie ;
4. ressaisir dans l'ordre, en conservant les heures réelles sur le support
   source lorsqu'elles ne peuvent pas être portées dans le champ applicatif ;
5. rapprocher chaque numéro temporaire du patient, de la prescription, du tube
   et du résultat RuggyLab ;
6. faire effectuer un second contrôle des données ressaisies ;
7. vérifier les valeurs critiques, rapports remis et doublons ;
8. marquer chaque ligne papier comme réconciliée, sans la détruire ;
9. archiver les documents selon la politique locale.

## 7. Sauvegarde et restauration

La restauration est une décision autorisée, effectuée par une personne
compétente à partir d'une sauvegarde vérifiée. Avant remise en production :

- contrôler la date du point de restauration ;
- identifier la période de données potentiellement manquantes ;
- tester l'intégrité et l'accès ;
- réconcilier toutes les opérations réalisées pendant l'interruption ;
- documenter la décision et le résultat.

Les sauvegardes et restaurations doivent faire l'objet d'essais périodiques.

## 8. Clôture de l'incident

Le responsable documente :

- cause et durée ;
- activités touchées ;
- nombre de dossiers traités manuellement ;
- écarts ou pertes détectés ;
- résultats critiques concernés ;
- délai de réconciliation ;
- actions correctives et responsables ;
- date du prochain test du plan.

