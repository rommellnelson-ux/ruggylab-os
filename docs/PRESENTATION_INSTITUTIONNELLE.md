# RuggyLab OS — Présentation institutionnelle

| Élément | Valeur |
|---|---|
| Nature | Système d'information de laboratoire (SIL) |
| Public | Direction, laboratoire, experts externes et partenaires techniques |
| Statut du document | Document de présentation à faire approuver localement |
| Version | 1.0 — juillet 2026 |

## 1. Finalité

RuggyLab OS accompagne le circuit du laboratoire depuis l'identification du
patient jusqu'à la diffusion d'un compte rendu. Il vise à réduire les erreurs
d'identification et de transcription, améliorer la traçabilité, accélérer le
traitement et rendre visibles les anomalies nécessitant une action.

RuggyLab OS est un outil d'appui. Il ne remplace ni les compétences du
personnel, ni les procédures qualité, ni la responsabilité médicale. Le projet
ne revendique ni certification, ni accréditation ISO 15189. Il propose des
fonctions pouvant contribuer à une démarche qualité qui doit être évaluée dans
le contexte complet du laboratoire.

## 2. Périmètre fonctionnel actuellement couvert

Le logiciel prend notamment en charge :

- les patients et leur identifiant permanent (IPP) ;
- les prescriptions d'examens ;
- les échantillons, codes-barres et numéros de laboratoire ;
- la saisie manuelle et certaines interfaces d'analyseurs ;
- le chargement des examens prescrits et le filtrage des équipements
  compatibles ;
- les intervalles de référence, indicateurs bas/haut et seuils critiques
  configurés ;
- le delta-check et certaines règles d'interprétation ;
- la validation opérationnelle et la file de revue biologique différée ;
- les comptes rendus versionnés et leur diffusion ;
- les exports FHIR, la qualité, les réactifs, les équipements, la facturation,
  l'épidémiologie et les indicateurs de délai.

Les unités calculables sont représentées avec UCUM et des codes LOINC sont
utilisés lorsqu'une correspondance est disponible. Leur présence facilite
l'interopérabilité mais ne garantit pas, à elle seule, la compatibilité avec un
système tiers.

## 3. Principes de sécurité clinique

Le fil directeur est :

`patient → prescription → échantillon → résultat → compte rendu`

Le logiciel :

- rattache chaque résultat à un échantillon ;
- charge dans l'interface les examens restant à réaliser selon la prescription
  liée ;
- refuse par API un examen non prescrit, un analyte étranger à l'examen ou un
  équipement déclaré incompatible ;
- ne produit pas un faux statut normal lorsqu'aucun intervalle biologique
  applicable n'est disponible ;
- bloque la sortie d'un compte rendu portant une valeur critique non acquittée ;
- conserve des snapshots versionnés des comptes rendus diffusés ;
- trace les actions sensibles dans le journal d'audit applicatif.

Les intervalles biologiques, seuils critiques, compatibilités d'appareils et
règles de validation doivent être approuvés et maintenus par le laboratoire.

## 4. Organisation des rôles

Les rôles techniques disponibles sont :

- **technician** : opérations de laboratoire dans son périmètre ;
- **officer** : revue biologique, correction et actions réservées ;
- **admin** : administration du système ;
- **accountant** : fonctions de gestion sans accès clinique.

Les comptes doivent être nominatifs. La matrice exacte des délégations et
responsabilités reste à faire approuver par la direction et le responsable
médical.

## 5. Position actuelle de la validation

Dans la configuration opérationnelle actuelle, la publication n'exige pas une
revue biologique immédiate. Un résultat produit selon le circuit autorisé peut
être rendu, puis demeure dans la file de revue biologique différée jusqu'à son
examen par un utilisateur habilité.

Cette organisation temporaire doit être décrite dans la procédure qualité
locale, approuvée par les responsables compétents et réévaluée lors du retour
d'un biologiste. Une valeur critique non prise en charge reste, elle,
bloquante.

## 6. Limites à déclarer aux évaluateurs

- La conformité d'un laboratoire ne peut pas être déduite du seul logiciel.
- Le fallback IA paludisme disponible sans modèle entraîné est heuristique et
  ne constitue pas une inférence clinique validée.
- La prise en charge critique trace actuellement l'utilisateur et l'heure de
  l'acquittement, mais pas encore toutes les informations d'une communication
  clinique complète (destinataire, moyen, heure d'appel, résultat de l'appel).
- Le journal d'audit est applicatif ; son caractère cryptographiquement
  inaltérable n'est pas revendiqué.
- Une connexion avec CSA PLATEAU ou DHIS2 nécessite une convention, un mapping,
  des tests et une autorisation avant usage réel.

## 7. Critères de réussite du projet

Le projet sera jugé utile si les utilisateurs constatent :

- moins de doublons et d'erreurs d'identité ;
- moins de résultats saisis hors prescription ;
- un traitement plus rapide et mieux traçable ;
- une identification immédiate des valeurs critiques ;
- des comptes rendus lisibles et cohérents ;
- une continuité de service documentée en cas d'incident ;
- des données agrégées fiables pour le pilotage.

