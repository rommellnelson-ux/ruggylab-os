# Intégration CSA PLATEAU

## Contrat retenu

- CSA PLATEAU est la source de l'identité administrative.
- `patient.id` CSA est l'identifiant technique externe immuable.
- `dossier_no` est le numéro lisible.
- RuggyLab conserve son propre IPP et une table de correspondance.
- Les prescriptions peuvent provenir d'un médecin, d'un infirmier habilité ou
  d'un technicien ; le rôle, l'origine et le motif sont conservés.

## Transport STAGING

Le connecteur authentifie un compte technique Supabase puis utilise uniquement :

- `csa_ruggylab_pull_prescriptions` pour lire les demandes structurées ;
- `csa_ruggylab_push_event` pour les reçus et résultats.

Les secrets restent dans `.env`. Le connecteur demeure inerte tant que les deux
options CSA ne sont pas activées et que la configuration n'est pas complète.

Routes :

- `GET /api/v1/csa-plateau/status` ;
- `GET/POST /api/v1/csa-plateau/exam-mappings` ;
- `POST /api/v1/csa-plateau/sync/prescriptions` ;
- `POST /api/v1/csa-plateau/results/{result_id}/push`.

Une prescription sans date de naissance ou sans mapping d'examen est rejetée
sans création partielle. Les répétitions sont idempotentes.

## État

Le connecteur reste **désactivé par défaut**. Lorsqu'il est explicitement activé
et complètement configuré, il utilise les RPC STAGING dédiées ; il ne lit jamais
directement les autres tables CSA.

Les routes réservées à l'administrateur permettent notamment :

- `GET /api/v1/csa-plateau/status` : vérifier la configuration sans exposer l'URL ;
- `POST /api/v1/csa-plateau/contract-test` : valider localement un exemple de
  contrat patient/prescription.

La recette locale génère une clé d'idempotence déterministe. Un second test du
même contrat est signalé comme rejoué et ne duplique pas l'événement d'audit.
L'audit ne contient ni nom, ni date de naissance, ni téléphone : uniquement la
clé, le nombre d'examens et la confirmation qu'aucun échange n'a eu lieu.

## Contrat minimal

Le patient possède un identifiant **dans le système source**, son identité,
date de naissance et sexe. Une prescription référence explicitement ce même
identifiant, sa date, sa priorité et une liste d'examens codés localement ou en
LOINC. RuggyLab conserve son propre identifiant interne : l'intégration future
devra utiliser une table de correspondance, jamais supposer que les identifiants
des deux systèmes sont identiques.

## Conditions avant le pilote

1. Migration Supabase appliquée uniquement dans STAGING.
2. Compte technique associé au profil `RUGGYLAB`.
3. Règles d'identitovigilance : doublons, collisions et rapprochement manuel.
4. Mapping versionné des patients, services, prescripteurs et examens.
5. Authentification forte, TLS, rotation des secrets et filtrage réseau.
6. Journalisation sans données nominatives et politique de conservation.
7. Tests d'idempotence, reprise, rejet, indisponibilité et réconciliation.
8. Recette par les techniciens et validation formelle avant production.

La recette commence par les prescriptions STAGING, puis teste le reçu et un
résultat synthétique avant tout usage de données réelles.
