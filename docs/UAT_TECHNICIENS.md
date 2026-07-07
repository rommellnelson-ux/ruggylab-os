# Protocole d'évaluation terrain — techniciens

## 1. Objet

Ce protocole évalue l'utilisation réelle de RuggyLab OS par les techniciens,
du dossier patient à la correction d'un résultat. Il ne constitue ni une
validation de méthode analytique, ni une preuve de conformité ISO 15189.

Les objectifs sont de mesurer :

- la réussite du circuit sans assistance ;
- le temps et le nombre d'erreurs par étape ;
- la compréhension des alertes et des statuts ;
- les contournements papier ou hors logiciel ;
- les risques potentiels pour le patient ;
- les améliorations demandées par les utilisateurs.

## 2. Conditions de l'essai

Utiliser exclusivement une instance UAT isolée avec des patients fictifs.
Ne jamais conduire cette campagne sur la base de production.

Préparer :

- un poste et un lecteur de codes-barres représentatifs du terrain ;
- un compte nominatif par technicien ;
- un compte officier/biologiste pour la correction ;
- un analyseur d'hématologie compatible NFS ;
- un appareil de biochimie ou POCT compatible glycémie ;
- les référentiels biologiques et correspondances de codes amorcés ;
- un observateur qui ne guide pas l'utilisateur, sauf blocage de sécurité.

Commande de contrôle préalable :

```powershell
python -m pytest -q tests/test_uat_technician_workflow.py
```

La campagne doit être arrêtée si l'identité d'un patient réel apparaît, si la
base UAT n'est pas isolée ou si un résultat peut être transmis hors de l'UAT.

## 3. Méthode de notation

Pour chaque scénario, l'observateur renseigne
`docs/templates/grille_retour_uat_techniciens.csv`.

Définitions :

- **réussi sans aide** : résultat attendu obtenu sans indication de
  l'observateur ;
- **réussi avec aide** : résultat obtenu après une ou plusieurs indications ;
- **échec** : résultat attendu non obtenu ou abandon ;
- **erreur critique** : erreur pouvant associer un résultat au mauvais
  patient, libérer une valeur critique non prise en charge ou masquer une
  correction ;
- **contournement** : utilisation nécessaire du papier, d'un tableur, d'une
  messagerie ou d'une autre application.

L'observateur note les faits, pas une impression générale. Exemple utile :
« Après le scan, le technicien a choisi Precis Expert pour la NFS ; l'appareil
n'était pas proposé. » Exemple insuffisant : « La machine fonctionne bien. »

## 4. Données fictives communes

Créer des identités clairement synthétiques, par exemple :

- patient : `UAT TECHNICIEN 01`, sexe féminin, née le 01/01/1990 ;
- prescription : NFS + GLYC ;
- tube conforme : `UAT-CONF-001` ;
- tube non conforme : `UAT-REJET-001`, aspect hémolysé ;
- valeurs NFS : normales, HGB basse à 8 g/dL, puis critique à 7 g/dL ;
- correction : HGB 8 g/dL vers 9 g/dL, motif documenté.

Les seuils ci-dessus servent à tester la configuration UAT livrée. Avant un
usage clinique, les seuils locaux doivent rester approuvés par le laboratoire.

## 5. Scénarios

### UAT-T01 — Patient et prescription

1. Rechercher le patient par IPP et par nom.
2. Vérifier l'absence de doublon.
3. Créer le patient fictif s'il n'existe pas.
4. Prescrire NFS et GLYC.
5. Vérifier les examens, l'identité et la priorité.

Résultat attendu : une seule identité, une prescription contenant exactement
NFS et GLYC.

### UAT-T02 — Échantillon conforme

1. Créer/scanner `UAT-CONF-001`.
2. Le rattacher à la prescription.
3. Renseigner l'aspect `conforme` et le statut `Recu`.
4. Ouvrir la saisie des résultats par code-barres.

Résultat attendu : l'échantillon est lié au bon patient et seuls NFS et GLYC
sont proposés.

### UAT-T03 — Échantillon non conforme

1. Créer `UAT-REJET-001`.
2. Renseigner l'aspect `hemolyse`.
3. Annuler l'échantillon selon la procédure locale.
4. Vérifier qu'il reste identifiable dans la traçabilité qualité.

Résultat attendu : le statut est `Annule`, l'aspect `hemolyse` est conservé et
le taux de non-conformité est mis à jour. Noter toute ambiguïté sur le motif.

### UAT-T04 — Sélection de l'appareil

1. Scanner le tube conforme.
2. Sélectionner NFS.
3. Examiner la liste des appareils.
4. Recommencer avec GLYC.
5. Tenter, si l'interface le permet, d'associer un appareil incompatible.

Résultat attendu : l'analyseur d'hématologie est proposé pour NFS, l'appareil
POCT/biochimie pour GLYC, et une association incompatible est refusée.

### UAT-T05 — Résultat normal

1. Saisir une NFS dans les intervalles de référence affichés.
2. Vérifier les unités avant enregistrement.
3. Ouvrir le détail du résultat.

Résultat attendu : absence de signal anormal ou critique inattendu, valeurs et
unités identiques entre saisie et détail.

### UAT-T06 — Résultat anormal non critique

1. Sur un nouveau dossier fictif, saisir HGB = 8 g/dL.
2. Enregistrer et ouvrir le détail.

Résultat attendu : HGB est signalée basse (`L`/`BAS`) mais non critique selon
la configuration UAT.

### UAT-T07 — Résultat critique

1. Sur un nouveau dossier fictif, saisir HGB = 7 g/dL.
2. Identifier l'alerte prioritaire.
3. Suivre la procédure de confirmation et de communication simulée.
4. Acquitter la valeur en indiquant uniquement des destinataires fictifs.

Résultat attendu : statut critique (`LL`), présence dans la file critique et
blocage de sortie tant que la prise en charge n'est pas tracée.

### UAT-T08 — Correction après contrôle

1. Ouvrir un résultat avec le rôle autorisé.
2. Corriger HGB de 8 à 9 g/dL.
3. Saisir le motif « Contrôle UAT — répétition analytique ».
4. Consulter l'audit et les éventuels rapports déjà produits.

Résultat attendu : valeur corrigée visible, motif et auteur tracés, ancienne
version/audit retrouvable et ancienne signature révoquée si applicable.

### UAT-T09 — Mode dégradé

1. Simuler l'indisponibilité du lecteur de codes-barres.
2. Rechercher le tube manuellement sans créer de doublon.
3. Simuler l'indisponibilité d'un appareil.
4. Appliquer la procédure locale sans inventer de résultat.

Résultat attendu : continuité contrôlée, identité préservée, aucune libération
non justifiée et étapes différées tracées.

## 6. Entretien de clôture

Poser les mêmes questions à chaque technicien :

1. Quelle étape vous a demandé le plus d'effort ?
2. Où craignez-vous le plus une erreur patient ?
3. Quelle information manque sur l'écran ?
4. Quelle alerte est ambiguë ou trop discrète ?
5. Quel papier ou outil externe reste indispensable ?
6. Quelle amélioration vous ferait gagner le plus de temps ?
7. Pourriez-vous former un collègue sur ce parcours ? Pourquoi ?

Ne pas rechercher un consensus pendant l'entretien. Conserver les réponses
individuelles avant la synthèse.

## 7. Critères de décision

Le pilote peut progresser si :

- 100 % des scénarios d'identité et de valeur critique sont réussis sans erreur
  critique ;
- au moins 90 % des tâches sont réussies sans aide après formation ;
- aucune machine incompatible ne peut être utilisée ;
- toutes les corrections restent attribuables et auditables ;
- tous les contournements sont documentés et évalués ;
- les anomalies à risque élevé ont un responsable et une date cible.

Une anomalie concernant l'identité, la criticité, la transmission ou
l'effacement d'une trace suspend le scénario concerné jusqu'à analyse.

## 8. Livrables de campagne

Conserver ensemble :

- la grille CSV complétée ;
- la version de RuggyLab testée ;
- la configuration des équipements et seuils ;
- le résultat des tests automatisés ;
- les captures ne contenant que des données fictives ;
- la synthèse des anomalies, décisions, responsables et échéances.

