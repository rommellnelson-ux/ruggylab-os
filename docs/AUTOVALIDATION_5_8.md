# Auto-validation ISO 15189 §5.8 — garde-fous et traçabilité

Ce document complète [`INTERPRETATION.md`](INTERPRETATION.md), qui fixe le
moteur d'interprétation faisant autorité. Il décrit les conditions dans
lesquelles RuggyLab OS positionne l'indicateur `is_auto_validated` et conserve la
trace d'une correction introduite le 20 juillet 2026.

## 1. Portée exacte

Le service `app/services/auto_validator.py` ne libère pas un compte-rendu. Il
positionne `Result.is_auto_validated`, indicateur exploité par le rapport de
conformité et l'historique patient. La validation technique, la signature et la
libération suivent leurs flux propres.

Une `AutoValidationConfig` active peut imposer :

| Condition | Champ | Effet |
|---|---|---|
| Aucune valeur critique | `require_not_critical` | `Result.is_critical` interdit l'auto-validation. |
| Aucun delta dépassé | `require_no_delta` | `Result.delta_exceeded` interdit l'auto-validation. |
| Tous les analytes couverts et normaux | `require_all_flags_normal` | Tout flag anormal ou analyte numérique non couvert provoque l'abstention. |

Le service ne commite pas la session ; l'appelant conserve la frontière
transactionnelle.

## 2. Garde-fou de couverture

`compute_flags` n'émet aucun flag pour un analyte qui ne possède pas de
`ReferenceRange` active. Vérifier uniquement les flags présents permettait donc
à un panel partiellement couvert de satisfaire à tort la condition « tous les
flags sont normaux ».

La fonction `_uncovered_analytes` compare désormais les analytes numériques de
`Result.data_points` aux clés de `Result.flags`. Une absence provoque
l'abstention. Les métadonnées connues, telles que `manual_entry_by`,
`entry_timestamp`, `calibration` et `overall_flags`, sont exclues.

Conséquence opérationnelle : chaque analyte d'un examen candidat à
l'auto-validation par flags doit posséder une plage de référence active. À
défaut, le résultat suit le circuit de validation normal.

## 3. Déterminisme

Lorsque plusieurs configurations sont actives, `_active_config` les ordonne par
identifiant décroissant. La configuration active la plus récente est donc
retenue de façon reproductible, au lieu de dépendre d'un `.first()` sans ordre
SQL garanti.

## 4. Vocabulaire accepté et moteur faisant autorité

`_is_normal_flag` reconnaît le vocabulaire court officiel (`N`) ainsi que
plusieurs formes longues acceptées défensivement (`NORMAL`, `NÉGATIF`).

Cette tolérance ne donne aucune autorité décisionnelle au référentiel `bioref`.
Au head contrôlé le 23 juillet 2026 :

- `compute_flags` reste le producteur officiel de `Result.flags` ;
- `check_critical` reste le producteur officiel du verdict critique numérique ;
- `apply_bioref_to_result` ne renseigne que `bioref_status`,
  `bioref_comment`, `bioref_reference_range` et `bioref_source` ;
- `apply_bioref_to_result` ne modifie ni `flags` ni `is_critical`.

En cas de divergence, le moteur officiel prime conformément à
[`INTERPRETATION.md`](INTERPRETATION.md).

## 5. Preuves et tests

Les preuves statiques principales sont :

- `app/services/auto_validator.py` : `_active_config`,
  `_uncovered_analytes`, `_is_normal_flag` et `try_auto_validate` ;
- `app/services/code_mapping_service.py` :
  `interpret_result_bioref` et `apply_bioref_to_result` ;
- `tests/test_auto_validation.py` : couverture incomplète, déterminisme,
  vocabulaire normal et requalification après amendement ;
- `docs/INTERPRETATION.md` : décision d'autorité entre le moteur officiel et
  `bioref`.

La CI cumulative de la PR #80 au commit `8562262` a exécuté 1 308 tests
applicatifs avec succès, puis la qualification corrective de la PR #100 a
réexécuté la suite complète, PostgreSQL, Docker, CodeQL et Playwright.

## 6. Traçabilité de la correction de juillet 2026

La correction initiale a été portée par :

- `a6fc8c0` — garde-fou de couverture, déterminisme et tolérance de vocabulaire ;
- `9accd7d` — formatage Ruff des tests.

Ces commits ont atteint `main` via la PR #55, dont l'intitulé ne décrivait pas ce
changement clinique. La branche distante choisie avait déjà servi à un autre
chantier.

Mesure de prévention : avant publication, vérifier l'existence de la branche
distante, comparer explicitement les commits à la base cible et contrôler que le
titre et le diff de la PR décrivent le même lot.

## 7. État du point de divergence ancien

Une version antérieure de ce document signalait un travail hors `main` qui
écrasait `Result.flags` et forçait `Result.is_critical` depuis `bioref`. Cette
divergence n'est pas présente dans le head de la PR #80 : le contrat additif est
explicitement codé et vérifié.

Le point est donc clos pour le code contrôlé. Toute future modification de
`apply_bioref_to_result` qui toucherait `flags` ou `is_critical` constituerait un
changement clinique et nécessiterait une décision documentée, des tests dédiés
et une qualification biologique.
