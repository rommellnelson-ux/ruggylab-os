# Dossier Go / No-Go — RuggyLab OS — 2026

## Verdict préparatoire

**NO-GO maintenu pour la fusion de la PR #80 et pour tout pilote clinique.**

Le lot #107 a corrigé et qualifié les comportements PR80-CLIN-01 :

- le qualitatif est non validé et non critique sans règle approuvée ;
- les routes POCT/Precix refusent toute saisie avant résultat, stock, seuil ou
  audit de succès tant qu'un profil appareil n'est pas qualifiable ;
- le fallback paludisme est supprimé et aucune inférence ne modifie `Result` ;
- DH36 et les listeners appareil sont désactivés par défaut ;
- le microscope n'est plus associé automatiquement par nom approximatif.

Ces corrections lèvent les scénarios dangereux du code, mais ne constituent
pas une homologation des appareils réels. Aucun protocole LIS n'est confirmé,
le modèle `Equipment` ne peut pas encore porter une qualification versionnée et
les décisions humaines restent ouvertes. Le parc est donc **NON ACTIVABLE EN
CLINIQUE**.

## Référence de qualification

- Base PR #80 : `main`, commit initial contrôlé `e96b63c`.
- Head applicatif initial : `8562262`.
- CI cumulative initiale : run `30032100788`, verte.
- Head après correctifs techniques : `f938030274045d61169e422f94819723b849c04f`.
- CI PR #80 après correctifs : run `30048611087`, verte.
- Documentation auto-validation : PR #104, CI `30048739217`, fusion `5f8b652`.
- Fail-closed interfaces/POCT/qualitatif/paludisme : PR #107, head `66c4ecf`,
  CI `30056391313` verte, fusion feature `631396d`.
- Dossier parc réel et commissioning : PR #108, head `12b953a`, CI
  `30057335660` verte, fusion feature `4c7fa35b`.
- Correctifs techniques :
  - PR #102 — formatage Ruff documentaire ;
  - PR #100 — Actions et Playwright Node 24 ;
  - PR #103 — test métriques déterministe ;
  - PR #101 — Pillow 12.3.0, CI `30047965217` verte, aucun avis connu.
- Contenu code + dossier qualifié : `4c7fa35b913037983c77e21f7510ac3a1717970f`,
  CI cumulative PR #80 `30078281184` verte : 1 311 tests réussis, 15 skips,
  PostgreSQL, Docker, CodeQL et Playwright réussis.
- Référence normative finale : le head courant de la PR #80. Toute modification
  postérieure, y compris de preuve, exige une nouvelle CI verte.

## Barrières avant pilote

| ID | Barrière | État | Preuve attendue | Responsable | Échéance |
|---|---|---|---|---|---|
| PIL-01 | PR80-CLIN-01 corrigé techniquement ; workflow cible à signer | Bloquant gouvernance | Revue PR #107 et matrice signée catégorie, rôle, validation, criticité, appareil/méthode. | Biologiste + qualité | Avant fusion/pilote |
| PIL-02 | D4 fail-closed implémenté ; modèle réel non homologué | Bloquant pour activation ML | Tests modèle absent/réel : aucune mutation clinique ; validation scientifique. | Biologiste + ML | Avant pilote |
| PIL-03 | D2 idempotence POCT/qualitatif | Bloquant pour ces flux | Clé d'acquisition et tests PostgreSQL de rejeu. | Intégration | Avant activation flux |
| PIL-04 | D3 ACK TCP durable | Bloquant pour TCP brut | Contrat instrument + test panne/reprise. | Biomédical/intégration | Avant listener réel |
| PIL-05 | D1 numéros explicites | Bloquant si import/HIS | Inventaire synthétique/copie autorisée et décision. | Laboratoire/DBA | Avant reprise |
| PIL-06 | Qualification serveur/réseau | Bloquant | Checklist INF/NET signée. | Exploitation/sécurité | Avant pilote |
| PIL-07 | Sauvegarde/restauration | Bloquant | Dump, SHA et rapport scratch `SUCCÈS`. | DBA | Avant pilote |
| PIL-08 | Référentiels cliniques | Bloquant | Sources, versions et signatures. | Biologiste | Avant pilote |
| PIL-09 | Réception synthétique | Bloquant | UAT complète sans données réelles. | Qualité | Avant pilote |
| PIL-10 | Worker/outbox | Bloquant pour diffusion | Instance unique, CLI alignée, passage supervisé. | Exploitation | Avant diffusion |
| PIL-11 | Registre Equipment | Bloquant appareils | Décision A/B, migration additive autorisée, données inconnues laissées nulles et interfaces désactivées. | Architecture + biomédical + qualité | Avant homologation |
| PIL-12 | DH36 réel | Bloquant interface | Manuel/protocole/firmware, mapping et commissioning signés. | Biomédical/intégration | Avant activation |
| PIL-13 | Dymind biochimie | Bloquant interface | Modèle exact et protocole propres, sans réutilisation DH36. | Biomédical/intégration | Avant activation |
| PIL-14 | Coagulation | Bloquant interface | Plaque, manuel, modèle, tests et éventuel protocole séparés. | Biomédical | Avant développement |
| PIL-15 | BIOSCANN CHEM 100 | Bloquant interface | Rôle RS-232/USB-B et format constructeur confirmés. | Biomédical/intégration | Avant driver |
| PIL-16 | Precix / ProCheck Expert | Bloquant POCT | Profil exact, unités/méthodes/CQ et catalogue homologués ; USB documenté. | Biologiste + POCT | Avant saisie/USB |
| PIL-17 | Microscope Magnus | Bloquant automatisation | Workflow humain supervisé ; aucune association ou décision automatique. | Biologiste + qualité | Avant usage intégré |

## Barrières avant production

| ID | Barrière | État | Preuve attendue | Responsable | Échéance |
|---|---|---|---|---|---|
| PROD-01 | D5 visibilité MADO | Bloquant multi-unité | Tests deux unités et rôle district. | Épidémiologie/sécurité | Avant production |
| PROD-02 | D6 FHIR pharmacie | Bloquant si exposé | Source persistée ou route désactivée. | Pharmacie/FHIR | Avant exposition |
| PROD-03 | D7 MFA privilégiée | Bloquant | Enrôlement ADMIN/OFFICER, récupération et break-glass. | Sécurité | Avant production |
| PROD-04 | D8 versions de résultats | Décision nécessaire | Plan d'implémentation et contrôle compensatoire signé. | Clinique/architecture | Avant politique définitive |
| PROD-05 | Audit DB immuable | Escalade | Permissions SQL/rétention/scellement approuvés. | DBA/sécurité | Avant production |
| PROD-06 | Annulation facture + BNPL | Escalade métier | Politique et tests. | Finance | Avant production |
| PROD-07 | Récupération de compte | Escalade sécurité | Procédure approuvée et auditée. | Sécurité/support | Avant production |
| PROD-08 | PRA/RPO/RTO | Bloquant | Exercice chronométré et accepté. | Exploitation | Avant production |
| PROD-09 | Formation/support | Bloquant | Feuilles, exercices, astreinte. | Direction/qualité | Avant production |

## Acceptable temporairement sous conditions

| Sujet | Condition compensatoire | Limite |
|---|---|---|
| `REQUIRE_VALIDATION_FOR_RELEASE=false` | Décision déjà consignée, critiques acquittées, procédure provisoire et supervision. | À renverser dès affectation d'un biologiste validateur. |
| Scopes OAuth déclaratifs inutilisés | Documenter que les rôles DB font autorité ; interdire toute nouvelle route scopée sans source serveur. | P3, aucun endpoint actuel ne doit se croire protégé par ces scopes. |
| Résultats amendés en place | Audit détaillé + snapshots/version de rapports + accès DB restreint. | Temporaire jusqu'à D8. |
| Audit non scellé en base | API lecture/export seulement et permissions SQL minimales. | Ne remplace pas une décision AUD-OPEN-01. |
| Tests ML skippés | D4 fail-closed et aucune fonction clinique activée. | Non acceptable si le flux ML est ouvert. |

## Décisions de gouvernance

| Décision | Choix attendu |
|---|---|
| PR80-CLIN-01 | Confirmer la correction fail-closed #107 et définir séparément tout futur workflow clinique. |
| D1 | Autorité et portée du numéro de laboratoire. |
| D2 | Clé d'idempotence d'acquisition. |
| D3 | Contrat ACK/retry et stockage durable. |
| D4 | Blocage clinique du fallback. |
| D5 | Unité et visibilité MADO. |
| D6 | Source et statut FHIR pharmacie. |
| D7 | Technologie et récupération MFA. |
| D8 | Modèle immuable de versions. |
| FIN-OPEN-01 | Annulation d'une facture avec plan BNPL actif. |
| AUTH-OPEN-03 | Récupération de compte. |
| AUD-OPEN-01 | Droits/immutabilité/rétention des audits. |
| EQUIP-DEC-01 | Choisir A (colonnes Equipment) ou B (sous-registres normalisés, recommandé) avant migration. |

Les options détaillées se trouvent dans
[`DECISION_PACK_P1_2026.md`](DECISION_PACK_P1_2026.md).

## Critères de passage au GO AVEC CONDITIONS pour PR #80

- [ ] CI finale verte sur le head exact.
- [ ] Aucun commentaire/revue bloquante.
- [ ] Pillow corrigé et `pip-audit` contrôlé.
- [x] Correction PR80-CLIN-01 fusionnée dans la branche feature et CI verte.
- [x] D4 explicitement fail-closed dans le code.
- [ ] Revue humaine de #107 et du dossier appareil terminée.
- [ ] CI finale verte sur le SHA incluant le présent dossier.
- [ ] Décision Equipment A/B enregistrée ; aucune migration implicite.
- [ ] Aucun appareil ni interface déclaré homologué ou activé.
- [ ] Méthode de fusion : merge commit pour préserver #85 à #99 et les lots
      correctifs.
- [ ] Aucun déploiement déclenché par la fusion.
- [ ] Rollback applicatif par digest/SHA préparé.
- [ ] D1 à D8 restent suivies avec responsables/échéances.

## Décision de comité

- [ ] GO fusion technique uniquement, sans déploiement.
- [ ] GO AVEC CONDITIONS listées : ______________________________
- [ ] NO-GO.

Décision : ______________________________________<br>
SHA autorisé : __________________________________<br>
Run CI : ________________________________________<br>
Risques acceptés : ______________________________<br>
Autorité clinique : _____________________________<br>
Exploitation/sécurité/qualité : _________________<br>
Date : _________________________________________
