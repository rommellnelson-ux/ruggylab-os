# Workflow de qualification Equipment — 2026

## Principe

Une identité, un port visible ou un parseur présent ne constituent jamais une
qualification. Le workflow est fail-closed et versionné :

```text
unqualified
  ├─ documentation_pending
  ├─ technical_testing
  └─ technically_qualified
          │ soumission ADMIN + snapshot complet
          ▼
clinical_review_pending
          │ approbation OFFICER|ADMIN
          ▼
clinically_approved
          │ activation distincte ADMIN
          ▼
qualifié mais désactivé ──► activé
          │                     │
          └──── suspension/désactivation OFFICER|ADMIN
                                ▼
                             suspended
```

Une nouvelle version lie `superseded_by_id`, désactive l'interface si besoin et
repart de `unqualified`. L'ancienne approbation reste visible mais n'est plus
utilisable.

## Construction du dossier

1. ADMIN enregistre l'identité technique sans fabriquer une valeur inconnue.
2. ADMIN enregistre une interface désactivée et ses versions connues.
3. ADMIN enregistre les métadonnées des documents autorisés.
4. ADMIN crée un brouillon et ajoute uniquement les analytes, méthodes, types
   d'échantillon et unités approuvés par les responsables compétents.
5. ADMIN soumet. Le service capture le snapshot et refuse tout dossier
   incomplet.
6. OFFICER ou ADMIN approuve explicitement le snapshot inchangé.
7. ADMIN demande séparément l'activation. Le service recalcule toutes les
   conditions et ajoute un audit dans la transaction.

L'approbation et l'activation peuvent être réalisées par la même personne si
elle possède les rôles nécessaires, mais restent deux actes distincts. Aucune
exigence maker-checker à deux personnes n'est décidée dans ce lot.

## Conditions d'activation

L'activation exige cumulativement :

- identité interne, fabricant, modèle, famille et firmware ;
- usage clinique déclaré et équipement non retiré ;
- interface connue, non archivée et direction compatible ;
- nom/version du protocole, driver/version et configuration ;
- qualification courante `clinically_approved`, non expirée, non suspendue et
  non remplacée ;
- correspondance exacte du snapshot avec l'identité et l'interface courantes ;
- au moins un analyte actif avec méthode, type d'échantillon et unité ;
- décision, approbateur, rôle, preuve et document existant non archivé ;
- rôle ADMIN pour l'activation ;
- audit `equipment.interface.enable` ajouté avant le commit.

Une seule condition absente produit une erreur structurée, conserve
`enabled=false` et ne crée ni résultat, stock, listener, port ou effet externe.

## Suspension et usage

OFFICER et ADMIN peuvent suspendre ou désactiver immédiatement. La suspension
désactive le flag dans la même transaction et conserve le dossier.

À chaque ingestion, RuggyLab recalcule la readiness : un flag historique ne
suffit pas. Le changement d'identité, firmware, interface, driver, protocole ou
configuration désactive l'interface et rend le snapshot non correspondant.
Une expiration temporelle produit le même refus.

Les codes d'analyte du message sont comparés au périmètre approuvé avant la
création de `Result`. DH36 exige en plus une identité d'équipement unique.

## Readiness et cockpit

La vue simple affiche exclusivement :

- NON QUALIFIÉ ;
- DOCUMENTATION MANQUANTE ;
- TEST TECHNIQUE ;
- APPROBATION CLINIQUE REQUISE ;
- SUSPENDU ;
- QUALIFIÉ MAIS DÉSACTIVÉ ;
- ACTIVÉ.

Le mot « opérationnel » n'est pas utilisé. La vue simple ne contient que des
catégories génériques de conditions manquantes. Les raisons détaillées sont
réservées à OFFICER et ADMIN.

## Commissioning réel

Le registre ne remplace pas l'identification physique, les droits sur les
manuels, les essais électriques/réseau, les trames certifiées, le mapping
clinique, le contrôle qualité, la formation, la décision Go/No-Go et la
signature finale. Aucun profil DH36, Dymind, coagulation, BIOSCANN ou
Precix/ProCheck n'est prérempli.
