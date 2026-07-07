# Validation locale du catalogue d'examens

Les consignes pré-analytiques et fiches techniques livrées dans RuggyLab OS
sont des **brouillons structurés**. Elles facilitent la préparation du
catalogue, mais ne remplacent ni les notices des réactifs et automates utilisés,
ni les procédures opératoires approuvées par le laboratoire.

## État vérifiable

Un responsable autorisé peut consulter :

```text
GET /api/v1/tat/catalog-audit
```

La réponse indique le nombre de fiches présentes, validées localement et encore
à valider. Par défaut, toutes les fiches portent
`validation_status: needs_local_validation`.

Une fiche ne peut être comptée comme validée que si elle contient :

- `validation_status: validated` ;
- `local_document_ref` : code et version de la SOP locale ;
- `validated_by` : identité ou fonction du valideur autorisé ;
- `validated_at` : date de validation.

## Revue à réaliser pour chaque examen

1. Confirmer le code, le libellé, la catégorie et, le cas échéant, le code
   LOINC avec le référentiel du laboratoire.
2. Vérifier le type d'échantillon, le contenant, les conditions de prélèvement,
   le transport, la conservation et les motifs de rejet.
3. Aligner les étapes analytiques sur l'automate, la méthode, les réactifs et
   leurs notices réellement utilisés.
4. Définir les contrôles qualité, leur fréquence et les règles d'acceptation
   selon le système qualité local.
5. Vérifier séparément la cible TAT, les unités, valeurs de référence et seuils
   critiques : ces éléments relèvent de référentiels distincts.
6. Faire approuver la SOP selon le circuit documentaire du laboratoire, puis
   renseigner ses métadonnées de validation dans le catalogue.

Ne jamais recopier une valeur clinique ou une procédure générique comme règle
locale sans revue et approbation documentées.
