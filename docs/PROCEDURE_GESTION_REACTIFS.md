# Procédure — Gestion des réactifs et consommables (RuggyLab OS)

Instruction opératoire pour le suivi des réactifs : référencement, réception par
lot (FEFO), consommation, péremption, réapprovisionnement et inventaire.
À afficher au magasin/paillasse. Conforme à l'esprit ISO 15189 (§4.6 achats,
§5.3 ressources).

---

## 1. Objet et périmètre
Garantir la **disponibilité** des réactifs, leur **traçabilité par lot** et
éviter les **ruptures** et l'usage de **réactifs périmés**. S'applique à tous les
réactifs et consommables critiques (tests, réactifs d'automate, etc.).

## 2. Rôles
| Rôle | Responsabilité |
|---|---|
| **Magasinier / technicien** | Réception des lots, sorties, inventaire, saisie des mouvements |
| **Officier / biologiste** | Validation des seuils, suivi des alertes, décision de commande |
| **Administrateur** | Référentiel réactifs, paramètres (seuils), supervision |

## 3. Principes directeurs
- **FEFO** (First-Expired-First-Out) : on consomme **toujours** le lot dont la
  **péremption est la plus proche**.
- **Stock de sécurité** : ne jamais descendre sous le seuil d'alerte ; viser une
  couverture (ex. 2 mois mini, 6 mois cible — modèle CMM OMS/MSF).
- **Traçabilité lot** : chaque réactif a un ou plusieurs **lots** (n° de lot +
  péremption + quantité).
- **Jamais de réactif périmé** en service : un lot périmé est retiré.

## 4. Deux niveaux dans RuggyLab
| Niveau | Rôle | Vue cockpit |
|---|---|---|
| **Réactif** (article) | Stock global, **seuil d'alerte**, péremption de référence, fournisseur, CMM | **📦 Stocks** |
| **Lot** | Traçabilité fine **FEFO** : n° lot, péremption, quantité, statut | **🧴 Lots réactifs (FEFO)** |

---

## 5. Procédures pas-à-pas

### 5.1 Référencer un réactif (une fois)
1. Vue **📦 Stocks** → renseigner : désignation, unité, **seuil d'alerte** (stock
   minimum), fournisseur.
2. *API* : `POST /api/v1/reagents`.
> Définir un **seuil d'alerte** réaliste = consommation pendant le délai de
> livraison + marge.

### 5.2 Réceptionner un lot (à chaque livraison) — FEFO
1. Vue **🧴 Lots réactifs (FEFO)** → « Réceptionner un lot » : **Réactif ID**,
   **n° de lot**, **date de péremption**, **quantité** → *Ajouter le lot*.
2. Répéter pour chaque lot reçu (un lot = une date de péremption).
3. *API* : `POST /api/v1/reagent-lots`.
> Toujours saisir la **péremption** : c'est elle qui pilote l'ordre FEFO.

### 5.3 Consommer / sortir un réactif
**a) Sortie manuelle (paillasse, contrôle) :**
1. Vue **🧴 Lots réactifs** → « Consommation FEFO » : Réactif ID + quantité →
   *Consommer*. Le système **décrémente d'abord le lot le plus proche de la
   péremption**, puis le suivant si besoin.
2. *API* : `POST /api/v1/reagent-lots/consume` (refus si quantité insuffisante).

**b) Sortie automatique liée à un résultat :**
- Lorsqu'un résultat est saisi, RuggyLab **décompte automatiquement** les
  réactifs selon les **ratios automate/réactif** configurés (consommation par
  analyse). La création est **refusée** si le stock est insuffisant.

### 5.4 Suivre les péremptions et les alertes
1. Vue **🧴 Lots réactifs** : liste **ordonnée FEFO** (péremption la plus proche
   en haut) ; un lot épuisé passe en statut `exhausted`.
2. Alertes péremption : *API* `GET /api/v1/reagents/expiring?days=30`.
3. Stock bas : tableau de bord `GET /api/v1/reports/stock-dashboard` (réactifs
   sous le seuil).
> Règle : retirer du service tout lot **périmé** ; consommer en priorité les
> lots **proches de la péremption**.

### 5.5 Réapprovisionner
1. Surveiller les **alertes de stock bas** (dashboard) et de **péremption**.
2. Calculer le besoin avec la **CMM** (Consommation Mensuelle Moyenne, modèle
   OMS/MSF) : `POST /api/v1/billing/cmm-report` → quantité suggérée pour viser la
   couverture cible (≈ 6 mois), priorise les ruptures imminentes (< 2 mois).
3. Prédiction de rupture / notifications : endpoints `/api/v1/stock/...`
   (prédicteur + notifications).
4. Passer commande ; à réception → **§5.2** (nouveau lot).

### 5.6 Inventaire, ajustement, pertes
- Inventaire physique périodique ; comparer au stock système.
- Toute **perte / casse / péremption** doit être tracée (mouvement de stock avec
  motif). Ne jamais corriger « en silence ».

---

## 6. Tableau de bord & indicateurs
- **Stock bas** : réactifs ≤ seuil (dashboard).
- **Péremptions ≤ 30 j** : liste des lots à surveiller.
- **Couverture (mois de stock)** via CMM.
- **Taux de perte / péremption** (indicateur qualité) à suivre dans le temps.

## 7. Mode dégradé (panne / coupure)
- Tenir une **fiche de casier papier** (n° lot, péremption, entrées/sorties,
  visa) par réactif critique.
- **Ressaisir** les mouvements dans RuggyLab dès le rétablissement.

## 8. Bonnes pratiques / erreurs à éviter
- ✅ Toujours saisir la **péremption** du lot (sinon FEFO inopérant).
- ✅ Consommer via la fonction **FEFO**, pas « au hasard ».
- ✅ Réceptionner **chaque** lot séparément (péremptions différentes).
- ❌ Ne pas laisser un lot **périmé** actif.
- ❌ Ne pas ajuster le stock sans **motif** tracé.
- ❌ Ne pas ignorer les alertes de stock bas (risque de rupture en pleine garde).

---

## Annexe — Récapitulatif API
| Action | Endpoint |
|---|---|
| Référencer / lister un réactif | `POST` / `GET /api/v1/reagents` |
| Modifier / supprimer un réactif | `PUT` / `DELETE /api/v1/reagents/{id}` |
| Réceptionner un lot | `POST /api/v1/reagent-lots` |
| Lister les lots (FEFO) | `GET /api/v1/reagent-lots?reagent_id=…` |
| Consommer (FEFO) | `POST /api/v1/reagent-lots/consume` |
| Réactifs proches péremption | `GET /api/v1/reagents/expiring?days=30` |
| Tableau de bord stock | `GET /api/v1/reports/stock-dashboard` |
| Calcul CMM / réappro | `POST /api/v1/billing/cmm-report` |
| Prédiction / notifications stock | `/api/v1/stock/…` |

*Voir aussi : [LIVRABLES_FORMATION_EXPLOITATION.md](LIVRABLES_FORMATION_EXPLOITATION.md).*
