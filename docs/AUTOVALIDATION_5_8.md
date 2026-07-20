# Auto-validation ISO 15189 §5.8 — garde-fous et traçabilité

> Complète [`INTERPRETATION.md`](INTERPRETATION.md), qui fixe **quel moteur fait
> autorité**. Le présent document décrit **à quelles conditions** un résultat
> peut être auto-validé, et consigne la correction du 2026-07-20.

## 1. Principe

L'auto-validation (`app/services/auto_validator.py`) ne *libère* pas un résultat :
elle pose l'indicateur `is_auto_validated`, exploité comme **indicateur qualité**
(taux d'auto-validation du rapport de conformité) et dans l'historique patient.
La validation technique et la revue biologique différée restent inchangées.

Une règle `AutoValidationConfig` active définit les conditions exigées :

| Condition | Champ | Effet |
|---|---|---|
| Aucune valeur critique | `require_not_critical` | `is_critical` bloque l'auto-validation |
| Aucun delta dépassé | `require_no_delta` | `delta_exceeded` bloque l'auto-validation |
| Tous analytes contrôlés et normaux | `require_all_flags_normal` | cf. §2 |

## 2. Garde-fou de couverture (correction 2026-07-20)

`compute_flags` **ignore silencieusement** tout analyte sans `ReferenceRange`
active : aucun flag n'est émis pour lui. Le contrôle « tous les flags sont
normaux » n'inspectant que les flags *présents*, un résultat pouvait s'auto-valider
alors qu'un analyte du panel n'avait **jamais été confronté à un critère
d'acceptation**.

Exemple : panel de 5 analytes dont 3 seulement possèdent une plage de référence
→ auto-validation accordée sur la foi de 3 analytes, les 2 autres pouvant porter
des valeurs aberrantes.

**Règle appliquée depuis la correction** — l'auto-validation s'abstient tant
qu'un analyte numérique de `data_points` n'a pas de flag résolu
(`_uncovered_analytes`). Les clés de métadonnées (`manual_entry_by`,
`entry_timestamp`, `calibration`, `overall_flags`) sont exclues du décompte.

> Conséquence opérationnelle : pour bénéficier de l'auto-validation par flags, il
> faut **déclarer une `ReferenceRange` pour chaque analyte** des examens
> concernés. À défaut, le résultat suit le circuit de validation normal — c'est
> le comportement voulu (abstention en cas de doute).

## 3. Déterminisme de la règle appliquée

En présence de plusieurs `AutoValidationConfig` actives, la règle retenue était
issue d'un `.first()` **non ordonné**, donc dépendante de l'ordre de lignes du
SGBD (non garanti en PostgreSQL). `_active_config` ordonne désormais par `id`
décroissant : **la règle active la plus récente s'applique**, de façon
reproductible et auditable.

## 4. Tolérance de vocabulaire (durcissement défensif)

`_is_normal_flag` accepte les jetons courts du moteur officiel (`N`) **et** les
formes longues (`NORMAL`, `NÉGATIF`).

Il s'agit d'un **durcissement défensif, non d'une correction de bug** : sur
`main`, `apply_bioref_to_result` renseigne uniquement les colonnes `bioref_*` et
ne touche ni `flags` ni `is_critical`, conformément à la décision figée
d'`INTERPRETATION.md`. Le moteur officiel reste donc seul producteur de `flags`.

## 5. Vérification

Constaté sur `origin/main` (`5cfaedf`), le 2026-07-20 :

- `tests/test_auto_validation.py` — 19 tests
- suites connexes (audit de conformité, valeurs critiques, delta-check, plages de
  référence, correction/péremption, TAT) — **119 tests au total : tous verts**
- `ruff check` : *All checks passed* ; `ruff format --check` : conforme

## 6. Traçabilité — écart de processus consigné

La correction a été portée par les commits :

- `a6fc8c0` — garde-fou de couverture, déterminisme, tolérance de vocabulaire
- `9accd7d` — formatage `ruff` du fichier de tests

Ces commits sont entrés dans `main` **via la PR #55, dont l'intitulé
(« Runtime séparé, reverse proxy TLS, CI E2E bloquante ») est sans rapport avec
l'ISO 15189** : le nom de branche retenu était déjà utilisé à distance par un
chantier antérieur. La correction n'a donc pas fait l'objet d'une revue dédiée et
l'historique ne reflète pas la nature clinique du changement.

**Mesure préventive** : vérifier `git ls-remote --heads origin '<motif>'` avant de
créer une branche, et contrôler que `git log origin/main..<branche>` est non vide
avant d'annoncer une PR.

## 7. Point ouvert — divergence à surveiller

Un travail en cours (hors `main`) réécrit `apply_bioref_to_result` pour qu'il
**écrase `result.flags` avec les statuts bioref longs et force `is_critical`**.
Cela contredit la décision figée d'`INTERPRETATION.md` §« Qui fait autorité ? »
(« sans modifier `flags` ni `is_critical` ») et transférerait au référentiel
d'aide un rôle décisionnel sur la validation et le circuit valeur critique.

À arbitrer explicitement avant fusion : soit le code revient au contrat figé,
soit la décision d'architecture est révisée **et documentée** comme telle.
