# Logique clinique des résultats

## Flux canonique

1. Une prescription contient les examens du catalogue.
2. Un échantillon du même patient est rattaché à la prescription.
3. L'écran **Résultats** charge uniquement les examens encore en attente.
4. Pour chaque examen, il construit les champs attendus et ne propose que les
   équipements compatibles.
5. L'API refuse un examen non prescrit, un analyte étranger à l'examen ou une
   machine incompatible.
6. Le résultat est interprété avec le référentiel biologique actif, puis la
   prescription est synchronisée.

Sans prescription liée, aucune saisie n'est proposée dans le cockpit. Les API
d'intégration automate restent disponibles pour les flux techniques autorisés.

## Standards de codage

- Examens et observations : codes LOINC lorsqu'ils sont disponibles.
- Unités calculables : codes UCUM (`g/L`, `g/dL`, `mmol/L`, `10*9/L`,
  `10*12/L`, `[IU]/L`, etc.).
- Échanges : FHIR R4 `DiagnosticReport` et `Observation`.

Les valeurs reçues sont converties vers l'unité du référentiel avant
interprétation. Une unité incompatible ne produit jamais un faux statut normal.

## Références et valeurs critiques

`BiologicalReferenceRange` est le référentiel canonique pour :

- la plage de référence ;
- le statut normal/bas/haut ;
- les seuils critiques bas et hauts.

Les seuils critiques sont inclusifs. Une valeur égale au seuil est donc
critique. Les tables historiques de plages et de seuils configurables restent
prises en charge comme surcharges locales de compatibilité.

Une plage d'un autre sexe ou une plage adulte ne sont jamais utilisées par
repli. En l'absence de plage applicable, RuggyLab affiche l'absence de
référence au lieu de produire un faux « OK ».

Les intervalles et seuils livrés sont des valeurs initiales documentées. Le
laboratoire doit valider et maintenir ses propres intervalles et seuils avec
les cliniciens conformément à sa procédure qualité.

## Compatibilité des équipements

- Dymind DH36 / hématologie : NFS.
- Precis Expert / POCT : glycémie, cholestérol total, acide urique.
- Analyseur d'ionogramme : ionogramme, calcémie.
- Biochimie / spectrophotomètre : biochimie courante.
- Sérologie / immunologie : examens sérologiques compatibles.
- Microscope / parasitologie : goutte épaisse, ECBU.
- Équipements spécialisés : VS, électrophorèse, groupage selon leur type.

Un type inconnu n'est pas déclaré compatible automatiquement. La saisie
manuelle reste possible et tracée.

Les examens complexes (Widal, groupage, électrophorèse, ECBU) disposent de
champs dédiés mais ne reçoivent pas une fausse plage numérique universelle.
