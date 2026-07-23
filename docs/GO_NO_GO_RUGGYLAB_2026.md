# Dossier Go / No-Go — RuggyLab OS — 2026

## Verdict préparatoire

**NO-GO temporaire pour fusion de la PR #80 et pour pilote clinique.**

La CI et les protections techniques corrigées sont solides, mais une règle
clinique nouvelle des flux d'acquisition n'est pas couverte par une décision
humaine :

- `submit_qualitative_result` marque tout résultat positif de catégorie
  `parasitology` comme critique ;
- la même route positionne `is_validated=True` et `validator_id` sur
  l'utilisateur actif non comptable ;
- le flux POCT générique applique le catalogue Precis Expert à tout couple
  modèle/série d'équipement enregistré sans prouver l'homologation de la méthode.

Ces comportements sont testés comme code, mais aucune approbation biologique de
leur portée n'a été trouvée. Le rapport d'audit affirmait par ailleurs qu'aucune
règle critique/diagnostique n'avait été modifiée, formulation trop large au
regard du diff d'acquisition.

Le verdict peut devenir **GO AVEC CONDITIONS pour la fusion technique**, sans
déploiement, lorsque l'autorité clinique :

1. approuve exactement ces sémantiques ; ou
2. ordonne leur restriction/correction dans une PR dédiée et qualifiée.

Le pilote et la production conservent leurs propres barrières ci-dessous.

## Référence de qualification

- Base PR #80 : `main`, commit initial contrôlé `e96b63c`.
- Head applicatif initial : `8562262`.
- CI cumulative initiale : run `30032100788`, verte.
- Head après correctifs techniques : `f938030274045d61169e422f94819723b849c04f`.
- CI PR #80 après correctifs : run `30048611087`, verte.
- Documentation auto-validation : PR #104, CI `30048739217`, fusion `5f8b652`.
- Correctifs techniques :
  - PR #102 — formatage Ruff documentaire ;
  - PR #100 — Actions et Playwright Node 24 ;
  - PR #103 — test métriques déterministe ;
  - PR #101 — Pillow 12.3.0, CI `30047965217` verte, aucun avis connu.
- Head applicatif final et run final : à remplacer après fusion des lots de
  qualification documentaire.

## Barrières avant pilote

| ID | Barrière | État | Preuve attendue | Responsable | Échéance |
|---|---|---|---|---|---|
| PIL-01 | Décision PR80-CLIN-01 sur qualitatif/POCT | Bloquant | Matrice signée catégorie, rôle, validation, criticité, appareil/méthode. | Biologiste + qualité | Avant fusion/pilote |
| PIL-02 | D4 fallback paludisme fail-closed | Bloquant | Test modèle absent : aucune écriture clinique. | Biologiste + ML | Avant pilote |
| PIL-03 | D2 idempotence POCT/qualitatif | Bloquant pour ces flux | Clé d'acquisition et tests PostgreSQL de rejeu. | Intégration | Avant activation flux |
| PIL-04 | D3 ACK TCP durable | Bloquant pour TCP brut | Contrat instrument + test panne/reprise. | Biomédical/intégration | Avant listener réel |
| PIL-05 | D1 numéros explicites | Bloquant si import/HIS | Inventaire synthétique/copie autorisée et décision. | Laboratoire/DBA | Avant reprise |
| PIL-06 | Qualification serveur/réseau | Bloquant | Checklist INF/NET signée. | Exploitation/sécurité | Avant pilote |
| PIL-07 | Sauvegarde/restauration | Bloquant | Dump, SHA et rapport scratch `SUCCÈS`. | DBA | Avant pilote |
| PIL-08 | Référentiels cliniques | Bloquant | Sources, versions et signatures. | Biologiste | Avant pilote |
| PIL-09 | Réception synthétique | Bloquant | UAT complète sans données réelles. | Qualité | Avant pilote |
| PIL-10 | Worker/outbox | Bloquant pour diffusion | Instance unique, CLI alignée, passage supervisé. | Exploitation | Avant diffusion |

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
| PR80-CLIN-01 | Approuver ou restreindre validation/criticité qualitatif et catalogue POCT générique. |
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

Les options détaillées se trouvent dans
[`DECISION_PACK_P1_2026.md`](DECISION_PACK_P1_2026.md).

## Critères de passage au GO AVEC CONDITIONS pour PR #80

- [ ] CI finale verte sur le head exact.
- [ ] Aucun commentaire/revue bloquante.
- [ ] Pillow corrigé et `pip-audit` contrôlé.
- [ ] PR80-CLIN-01 signée ou correction fusionnée.
- [ ] D4 explicitement bloquée dans tout profil clinique.
- [ ] Méthode de fusion : merge commit pour préserver #85 à #99 et les lots
      correctifs.
- [ ] Aucun déploiement déclenché par la fusion.
- [ ] Rollback applicatif par digest/SHA préparé.
- [ ] D1 à D8 restent suivies avec responsables/échéances.

## Décision de comité

- [ ] GO fusion technique uniquement, sans déploiement.
- [ ] GO AVEC CONDITIONS listées : ______________________________
- [ ] NO-GO.

Décision : ______________________________________  
SHA autorisé : __________________________________  
Run CI : ________________________________________  
Risques acceptés : ______________________________  
Autorité clinique : _____________________________  
Exploitation/sécurité/qualité : _________________  
Date : _________________________________________
