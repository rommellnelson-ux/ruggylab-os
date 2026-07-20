# Moteurs d'interprétation biologique — rôles et autorité

RuggyLab OS comporte **trois référentiels** d'interprétation. Ils sont
volontairement **distincts et complémentaires** : ce document fixe lequel fait
**autorité** sur le verdict d'un résultat, pour éviter toute ambiguïté.

## Vue d'ensemble

| Moteur | Vocabulaire | Sortie | Rôle |
|---|---|---|---|
| `ReferenceRange` + `compute_flags` | analytes (`WBC`, `HGB`…) | flags `HH/H/N/L/LL` | **Officiel** — pilote la validation et l'auto-validation §5.8 |
| `CriticalRange` + `check_critical` | analytes | `is_critical` (bool) | **Officiel** — déclenche le circuit valeur critique |
| `bioref` (`BiologicalReferenceRange`) | `test_code` (`HB`, `GLU_FAST`…) | `NORMAL/BAS/HAUT/CRITIQUE` + commentaire + source | **Aide à l'interprétation** — couche additive, n'altère pas le verdict |

## Qui fait autorité ?

**Le verdict officiel d'un résultat repose sur `ReferenceRange` et
`CriticalRange`** :
- les `flags` (HH/H/N/L/LL) calculés par `compute_flags` conditionnent
  l'auto-validation (`require_all_flags_normal`) et l'affichage clinique ;
- `is_critical`, calculé par `check_critical`, déclenche l'acquittement, les
  alertes et le rapport de conformité.

**`bioref` est une couche d'aide complémentaire**, jamais le verdict :
- elle renseigne uniquement les colonnes `bioref_status`, `bioref_comment`,
  `bioref_reference_range`, `bioref_source` du résultat ;
- elle apporte une interprétation clinique sourcée (IFCC/Tietz, OMS…), riche et
  stratifiée par sexe/âge, **sans modifier** `flags` ni `is_critical` ;
- elle est exposée par les endpoints `/bioref/*` et `/results/{id}/bioref`.

> Règle : si `bioref` et le moteur officiel divergent, **le moteur officiel
> prime** pour toute décision (validation, critique, conformité). `bioref` sert
> d'éclairage au biologiste, pas de juge.

## Le rôle de la table de correspondance (`biological_code_mappings`)

Les trois vocabulaires ne partagent pas les mêmes codes (`GE` vs `MAL_GE`,
`GLYC` vs `GLU_FAST`, panel `NFS` vs composants `HB/HT/WBC`…). La table
`biological_code_mappings` relie `exam_code` ↔ `test_code` ↔ `analyte` **dans le
seul but de brancher l'aide bioref** sur un résultat. Elle ne fusionne pas les
moteurs et ne change pas l'autorité décrite ci-dessus.

## Comment ajouter un nouvel examen

1. **Catalogue d'examens** (`app/services/exam_catalog.py`) : ajouter le code
   d'examen (`exam_code`), libellé, catégorie, LOINC, cible TAT.
2. **Référentiel bioref** (`app/services/bioref_data.py`) : ajouter la ou les
   valeurs de référence (par sexe/âge) avec bornes, seuils critiques, source.
3. **Correspondance** (`app/services/code_mapping_data.py`) : relier
   `exam_code` ↔ `test_code` (+ `analyte_code` si besoin).
4. **Moteur officiel** (optionnel, si l'examen doit produire un flag/critique
   automatique) : créer les `ReferenceRange` et `CriticalRange` correspondants
   (via les endpoints d'administration ou un seed).

## Comment mapper un panel (ex. NFS, IONO)

- Déclarer le panel dans `code_mapping_data` avec `is_panel=True`.
- Déclarer chaque composant avec `component_of=<code_panel>` et son `analyte_code`.
- L'interprétation bioref se fait alors **composant par composant**
  (`interpret_result_bioref`) ; le panel lui-même n'est pas interprété comme une
  valeur unique.

## Décision d'architecture (figée)

Option retenue : **conserver `ReferenceRange`/`CriticalRange` comme moteur
officiel** et **`bioref` comme couche d'aide**. Une unification totale (bioref
source unique) a été écartée : gain surtout esthétique pour un risque clinique
réel (migration du moteur de validation). Le cloisonnement reste donc clair et
testé en l'état.

Les conditions dans lesquelles les `flags` du moteur officiel autorisent une
auto-validation §5.8 sont détaillées dans
[`AUTOVALIDATION_5_8.md`](AUTOVALIDATION_5_8.md).
