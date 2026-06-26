# Unification des vocabulaires biologiques

## Le problème : trois vocabulaires de codes

RuggyLab OS manipule un examen biologique sous **trois identifiants différents**,
hérités de modules construits indépendamment :

| Vocabulaire | Où | Exemples | Pilote |
|---|---|---|---|
| **`exam_code`** | `exam_catalog`, `TatTarget`, registre, `Result.exam_code` | `NFS`, `GE`, `GLYC`, `CREAT` | catalogue d'examens, TAT, épidémio |
| **`test_code`** | `BiologicalReferenceRange` (référentiel IFCC/Tietz/OMS) | `HB`, `MAL_GE`, `GLU_FAST`, `CREAT` | interprétation clinique (NORMAL/BAS/HAUT/CRITIQUE) |
| **`analyte`** | `data_points` des résultats, `ReferenceRange`, `CriticalRange` | `HGB`, `WBC`, `GLYC` | flags HH/H/N/L/LL, statut critique |

Un même examen porte donc des codes incohérents : `GE` (catalogue) vs `MAL_GE`
(référentiel), `GLYC` vs `GLU_FAST`, `ASAT` vs `AST`, `HGB` (analyte) vs `HB`
(test_code). Sans pont, l'interprétation clinique riche du référentiel ne peut
pas s'appliquer aux résultats.

## La solution : un `canonical_code` + une table de correspondance

La table **`biological_code_mappings`** relie les trois vocabulaires autour d'un
**code canonique** stable. Chaque ligne déclare, pour un examen ou un composant :

- `canonical_code` — l'identifiant pivot (ex. `GLYC`, `HB`, `NA`).
- `exam_code`, `test_code`, `analyte_code` — les équivalents dans chaque vocabulaire (nullable).
- `component_of` — le code canonique du **panel** parent (pour les composants).
- `is_panel` — vrai pour un panel (NFS, IONO) qui n'est **pas** interprété comme une valeur unique.
- `priority`, `is_active`, métadonnées (`label`, `category`, `specimen_type`, `unit`).

Le `canonical_code` est le point d'ancrage : on résout depuis n'importe quel
vocabulaire vers lui, puis on redescend vers le `test_code` du référentiel pour
produire l'interprétation.

## Rétrocompatibilité (garanties)

- **Aucun moteur existant n'est modifié** : `ReferenceRange + compute_flags` et
  `CriticalRange + check_critical` continuent de produire flags et `is_critical`.
- L'interprétation bioref est **purement additive** : nouveaux champs
  `bioref_status`, `bioref_comment`, `bioref_reference_range`, `bioref_source`
  sur `Result` (nullable), plus l'endpoint `GET /results/{id}/bioref`.
- **Sans correspondance, comportement inchangé** : si aucun mapping ne résout
  l'`exam_code`, les champs bioref restent nuls.
- Les anciens codes ne sont **pas supprimés** ; la couche est progressive.

## Flux à la création d'un résultat

1. Le résultat est créé avec un `exam_code` (ex. `GLYC`).
2. `resolve_from_exam_code` cherche le mapping ; absent → on s'arrête (rien ne change).
3. Test simple → on lit la valeur dans `data_points`, on interprète via le
   `test_code` bioref, on renseigne les colonnes `bioref_*`.
4. Panel (ex. `NFS`) → colonnes plates laissées nulles ; le détail **par composant**
   est fourni par `GET /results/{id}/bioref`.

## Panels

Un panel (`is_panel=True`) n'a pas de valeur unique. Ses composants sont des
lignes de mapping avec `component_of` pointant sur le panel :

- **NFS** → `HB`, `HT`, `WBC`, `PLT`, `RBC`, `MCV`, `MCH`, `MCHC` (interprétés
  individuellement, ex. Hb basse → `BAS`).
- **IONO** → `NA`, `K`, `CL`, `CA`, `MG`.

Les codes référentiel variant selon le sexe (`URIC_H`/`URIC_F`, `RBC_H`/`RBC_F`)
sont résolus automatiquement : le service tente `test_code`, puis `test_code_H` /
`test_code_F` selon le sexe du patient.

## Comment ajouter un nouvel examen

1. (Si besoin) ajouter la valeur de référence dans `bioref_data.py` (`test_code`).
2. (Si besoin) ajouter l'examen dans `exam_catalog.py` (`exam_code`).
3. Ajouter une correspondance, soit par l'API/interface admin, soit dans
   `code_mapping_data.py` :
   ```python
   _m("MONCODE", exam="MONEXAM", test="MONTEST", analyte="MONANALYTE",
      label="Mon examen", category="Biochimie", unit="g/L")
   ```
4. Recharger les correspondances : `POST /code-mappings/seed-defaults` (idempotent).

## Comment mapper un panel

```python
_m("PANEL", exam="PANEL", label="Mon panel", category="…", is_panel=True, priority=10)
_m("COMP1", test="COMP1", analyte="ANALYTE1", component_of="PANEL", label="…")
_m("COMP2", test="COMP2", analyte="ANALYTE2", component_of="PANEL", label="…")
```

Le panel porte `is_panel=True` ; chaque composant référence le panel via
`component_of` et fournit son `test_code` (référentiel) + `analyte_code` (clé
attendue dans `data_points`).

## API

| Endpoint | Rôle |
|---|---|
| `GET /code-mappings` | liste des correspondances actives |
| `POST /code-mappings` | créer (officier) |
| `DELETE /code-mappings/{id}` | désactiver (officier) |
| `POST /code-mappings/seed-defaults` | charger les correspondances prioritaires (officier) |
| `POST /code-mappings/test` | tester une résolution `exam_code[, analyte_code]` |
| `GET /code-mappings/orphans` | codes catalogue/référentiel sans correspondance |
| `GET /results/{id}/bioref` | interprétation bioref complémentaire (par composant si panel) |

Interface : panneau **« 🔗 Unification des vocabulaires biologiques »** dans la vue
Résultats du cockpit (test de mapping, table filtrable, codes orphelins).
