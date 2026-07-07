# Passerelle DHIS2 agrégée — phase pilote

## Portée livrée

Cette première phase prépare des rapports mensuels agrégés sans transmettre de
donnée nominative et sans appeler automatiquement une instance DHIS2.

Le circuit est :

`mappings → prévisualisation → snapshot calculé → validation humaine → CSV/JSON`

Une indisponibilité de DHIS2 ne peut donc pas bloquer le fonctionnement du
laboratoire.

## Indicateurs pilotes

- `LAB_ACT_TOTAL` : résultats validés pendant la période ;
- `MAL_TEST_TOTAL` : résultats paludisme finalisés ;
- `MAL_POS_TOTAL` : résultats paludisme positifs ;
- `PRE_REJECT_TOTAL` : prélèvements rejetés ;
- `CRIT_NOTIFIED` : résultats critiques dont l'acquittement est tracé.

Les définitions doivent être approuvées par le responsable métier et comparées
aux rapports manuels avant toute utilisation institutionnelle.

## Routes protégées

- `GET /api/v1/integrations/dhis2/mappings` : mappings actifs, administrateur ;
- `POST /api/v1/integrations/dhis2/mappings` : créer un mapping, administrateur ;
- `GET /api/v1/integrations/dhis2/preview` : prévisualiser une période ;
- `POST /api/v1/integrations/dhis2/exports` : figer un export calculé ;
- `POST /api/v1/integrations/dhis2/exports/{id}/validate` : validation humaine ;
- `GET /api/v1/integrations/dhis2/exports` : historique ;
- `GET /api/v1/integrations/dhis2/exports/{id}.csv` : export de contrôle.

Les identifiants DHIS2 sont des UID de onze caractères provenant de l'instance
cible. Aucun UID d'exemple ne doit être utilisé en production.

## Garanties de la phase pilote

- absence de nom, IPP, téléphone, date de naissance ou code-barres dans le
  payload agrégé ;
- empreinte SHA-256 du contenu ;
- déduplication d'un export strictement identique ;
- mappings configurables et datables ;
- opérations sensibles auditées ;
- rejet d'un export si un mapping est manquant ;
- aucun secret DHIS2 stocké dans ces tables ;
- aucun envoi réseau automatique.

## Conditions avant ajout de l'envoi API

1. Obtenir une instance de test, l'URL, le Data Set, l'Organisation Unit, les
   Data Elements et éventuels Category Option Combos.
2. Faire approuver les définitions des indicateurs.
3. Réaliser plusieurs périodes de comparaison avec le rapport manuel.
4. Définir le compte technique, ses privilèges minimaux et la rotation du
   secret.
5. Valider les procédures d'erreur, de correction, de reprise et de
   réconciliation.
6. Obtenir l'autorisation institutionnelle avant tout envoi officiel.

Le Tracker individuel reste hors périmètre de cette phase.
