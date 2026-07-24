# Dossier du comité Go/No-Go — RuggyLab OS — 2026

## 1. Résumé exécutif

### Décision préparatoire

**NO-GO clinique et opérationnel maintenu.**

La PR
[#80](https://github.com/rommellnelson-ux/ruggylab-os/pull/80) est ouverte
de `feat/acquisition-3-flux` vers `main`. Son head de référence est
`e71d57013abea71377fcce5ea68a7f2a0c5125ed`. La CI cumulative
`30089902694` est verte sur ce SHA.

Cette qualification technique confirme les tests, migrations et barrières
logicielles. Elle ne vaut ni :

- approbation de fusion par le comité ;
- préparation automatique d'une préproduction ;
- homologation ou commissioning d'un appareil ;
- autorisation de pilote clinique ;
- autorisation de déploiement ;
- remise en service du worker d'outbox.

Le registre `Equipment` normalisé, intégré par la PR
[#110](https://github.com/rommellnelson-ux/ruggylab-os/pull/110), lève un
défaut de gouvernance logicielle. Il apporte identité, interfaces,
qualifications versionnées, périmètres analytiques, documents, RBAC,
readiness et activation fail-closed. La migration `20260724_0039` ne crée
aucune donnée ou qualification réelle et laisse les interfaces désactivées.

Les comportements dangereux historiques de la PR #80 sont corrigés :

- qualitatif non validé, sans validateur implicite et non universellement
  critique ;
- POCT fail-closed, sans valeur absente générée ni catalogue non homologué ;
- listeners DH36/gateway désactivés et parseurs stubs si protocole inconnu ;
- paludisme sans fallback heuristique ni mutation clinique ;
- contrôles Equipment appliqués à l'activation et à l'usage.

Les décisions D1, D2, D3, D5, D6, D7 et D8 restent ouvertes. Les risques
`FIN-OPEN-01`, `AUTH-OPEN-03`, `AUD-OPEN-01`, `EQUIP-OPEN-01` et
`EQUIP-OPEN-02` restent ouverts. Aucun appareil du parc n'est `ACTIVABLE`.

### Recommandation au comité

Ne considérer aucune des décisions A à D ci-dessous comme implicitement liée à
une autre. À la date de ce dossier :

- **A — fusion technique vers `main` : NO-GO maintenu** jusqu'à décision
  humaine formelle ;
- **B — préparation d'une préproduction : NO-GO d'exécution**, dossier
  préparatoire seulement ;
- **C — commissioning d'un appareil : NO-GO**, aucun appareil déterminé ne
  possède toutes les preuves ;
- **D — remise en service du worker : NO-GO**, traitement séparé requis.

## 2. Références vérifiées

| Élément | Référence |
|---|---|
| PR d'intégration | #80, ouverte, non fusionnée, base `main` |
| Head PR #80 | `e71d57013abea71377fcce5ea68a7f2a0c5125ed` |
| PR Equipment | #110, fusionnée dans `feat/acquisition-3-flux` |
| Head Alembic | `20260724_0039`, parent `20260723_0038` |
| CI cumulative | `30089902694`, succès |
| Description PR #80 | Actualisée pour le head et le NO-GO courants |
| Publication d'image | Skippée par la condition tag/manuelle ; aucune publication par ce run |

L'état GitHub `CLEAN` ou `mergeable` indique seulement l'absence de conflit
technique connu. Il ne constitue pas une approbation.

## 3. État technique

### Acquis

- architecture FastAPI/PostgreSQL et chaîne Alembic linéaire ;
- garde-fous transactionnels, RBAC et audits atomiques ;
- échantillon annulé terminal et contrôles avant effets ;
- idempotence automate/DH36 pour les flux déjà dotés d'une clé ;
- rapports signés par snapshots et outbox persistante ;
- interfaces appareil désactivées par défaut ;
- registre Equipment versionné et contrôlé à l'usage ;
- rollback d'audit/commit testé ;
- dépendances, CodeQL et stack Docker contrôlés en CI.

### Limites

- D1 : politique des numéros explicites non décidée ;
- D2 : clé d'acquisition qualitatif/futur POCT non décidée ;
- D3 : durabilité avant ACK TCP non décidée ;
- droits SQL append-only des audits et qualifications non décidés ;
- infrastructure, réseau, secrets, sauvegarde/restauration et PRA réels non
  qualifiés ;
- aucun protocole constructeur réel confirmé.

## 4. État clinique

### Protections présentes

- résultat qualitatif non validé et sans criticité universelle ;
- POCT refusé avant appareil/méthode/unité/catalogue qualifiés ;
- absence de modèle paludisme : échec explicite ;
- inférence paludisme : aucune mutation de `Result` ;
- aucune validation biologique implicite à l'acquisition ;
- règles critiques et référentiels non modifiés par ce lot.

### Barrières restantes

- qualification et signature des référentiels cliniques ;
- décisions D5 et D6 pour les périmètres MADO/FHIR pharmacie ;
- D7 avant production pour les comptes privilégiés ;
- D8 pour la politique définitive d'amendement ;
- revue clinique et UAT synthétique ;
- autorisations humaines signées.

## 5. État des équipements

| Appareil | Identité/documentation | Registre/driver | Statut |
|---|---|---|---|
| [Dymind DH36](devices/DYMIND_DH36_DEVICE_PROFILE.md) | Modèle connu, protocole et manuel LIS absents | Ingestion protégée, listeners désactivés | **DOCUMENTATION MANQUANTE** |
| [Dymind Semi-auto Chemistry](devices/DYMIND_SEMIAUTO_CHEMISTRY_DEVICE_PROFILE.md) | Modèle exact inconnu | Stub distinct du DH36 | **NON IDENTIFIÉ** |
| [Coagulation](devices/COAGULATION_UNIDENTIFIED_DEVICE_PROFILE.md) | Marque/modèle/manuels inconnus | Aucun driver qualifié | **NON IDENTIFIÉ** |
| [Anbio / BIOSCANN CHEM 100](devices/BIOSCANN_CHEM100_DEVICE_PROFILE.md) | Modèle observé, communication inconnue | Stub désactivé | **DOCUMENTATION MANQUANTE** |
| [Precix / ProCheck Expert](devices/PRECIX_PROCHECK_EXPERT_DEVICE_PROFILE.md) | Dénomination exacte et notice à confirmer | POCT fail-closed | **NON IDENTIFIÉ** |
| [Magnus Epiled Theia-I MLXi](devices/MAGNUS_EPILED_THEIA_MLXI_DEVICE_PROFILE.md) | Modèle communiqué, imagerie/documentation incomplètes | Workflow humain, ML fail-closed | **DOCUMENTATION MANQUANTE** |
| [ZJZD-III](devices/ZJZD_III_OSCILLATOR_DEVICE_PROFILE.md) | Modèle et manuel observés | Aucun driver requis | **NON QUALIFIÉ** |
| [Centrifugeuse 80-2](devices/CENTRIFUGE_80_2_DEVICE_PROFILE.md) | Modèle de manuel observé, rotor/métrologie à confirmer | Aucun driver requis | **NON QUALIFIÉ** |

Aucun appareil n'est marqué `QUALIFIÉ MAIS DÉSACTIVÉ` ou `ACTIVABLE`.

## 6. État du worker d'outbox

Observation en lecture seule du 24 juillet 2026 à 12:27:53 UTC :

- tâche Windows présente et état `Ready` ;
- aucun processus correspondant observé ;
- dernier résultat `0xC000013A` ;
- prochaine tentative alors planifiée à 12:32:52 UTC ;
- aucune modification, désactivation, relance ou réinstallation effectuée.

Le dossier
[`INCIDENT_WORKER_PLANIFIE_2026-07-23.md`](INCIDENT_WORKER_PLANIFIE_2026-07-23.md)
explique l'incompatibilité entre l'action installée et la CLI courante, ainsi que
la procédure préparée mais non autorisée. L'état réel de la file reste inconnu,
aucune base n'ayant été interrogée.

## 7. Migrations

La chaîne qualifiée atteint `20260724_0039` :

- migration additive du registre Equipment ;
- aucun backfill, appareil ou profil créé ;
- `upgrade`, `downgrade → upgrade` et tests PostgreSQL réussis ;
- aucune migration supplémentaire dans le présent lot documentaire.

Une CI verte sur une base jetable ne prouve pas la compatibilité de données
historiques réelles.

## 8. CI de référence

Run `30089902694` sur `e71d57013abea71377fcce5ea68a7f2a0c5125ed` :

| Contrôle | Résultat |
|---|---|
| Suite principale | 1 345 réussis, 17 skips, 13 warnings |
| PostgreSQL 16 | 13 réussis, migrations, concurrence, smoke et flux E2E |
| Ruff, format, mypy, Bandit | Succès |
| Audit de dépendances | Aucune vulnérabilité connue détectée |
| Docker production | Succès en environnement CI |
| CodeQL | Succès |
| Playwright | Succès |
| Publication d'image | Skippée ; aucune image publiée |

Ces résultats sont des preuves de qualification technique du SHA, pas des
preuves de qualification d'un appareil ou d'un site.

## 9. Registre des décisions à signer

| Décision/risque | Issue | Décision attendue |
|---|---|---|
| D1 / LAB-OPEN-01 | [#111](https://github.com/rommellnelson-ux/ruggylab-os/issues/111) | Autorité, namespace et unicité des numéros explicites |
| D2 / ACQ-OPEN-01 | [#112](https://github.com/rommellnelson-ux/ruggylab-os/issues/112) | Clé d'acquisition et réponse au rejeu |
| D3 / ACQ-OPEN-02 | [#113](https://github.com/rommellnelson-ux/ruggylab-os/issues/113) | Durabilité et contrat ACK/retry |
| D5 / EPI-OPEN-01 | [#114](https://github.com/rommellnelson-ux/ruggylab-os/issues/114) | Unité et visibilité MADO |
| D6 / FHIR-OPEN-01 | [#115](https://github.com/rommellnelson-ux/ruggylab-os/issues/115) | Source persistée et statut FHIR pharmacie |
| D7 / AUTH-OPEN-01 | [#116](https://github.com/rommellnelson-ux/ruggylab-os/issues/116) | MFA, récupération et break-glass |
| D8 / RESULT-OPEN-01 | [#117](https://github.com/rommellnelson-ux/ruggylab-os/issues/117) | Modèle immuable des résultats |
| FIN-OPEN-01 | [#118](https://github.com/rommellnelson-ux/ruggylab-os/issues/118) | Facture annulée et plan BNPL actif |
| AUTH-OPEN-03 | [#119](https://github.com/rommellnelson-ux/ruggylab-os/issues/119) | Récupération de compte |
| AUD-OPEN-01 | [#120](https://github.com/rommellnelson-ux/ruggylab-os/issues/120) | Droits SQL, rétention et immutabilité des audits |
| EQUIP-OPEN-01 | [#121](https://github.com/rommellnelson-ux/ruggylab-os/issues/121) | Commissioning appareil par appareil |
| EQUIP-OPEN-02 | [#122](https://github.com/rommellnelson-ux/ruggylab-os/issues/122) | Protection SQL complémentaire Equipment |

Chaque issue reste ouverte, sans responsable assigné ni échéance inventée.

## 10. Risques acceptés

`GOV-ACCEPT-01` consigne temporairement
`REQUIRE_VALIDATION_FOR_RELEASE=false`, avec critiques acquittées, procédure
provisoire et supervision. Cette acceptation :

- ne s'étend pas aux nouveaux flux POCT/qualitatifs/appareils ;
- ne remplace pas une validation biologique ;
- doit être réévaluée avant pilote ;
- doit être renversée dès l'affectation d'un biologiste validateur.

Les scopes OAuth déclaratifs actuellement inutilisés restent un sujet P3
(`AUTH-OPEN-02`) ; les rôles en base font autorité.

## 11. Risques ouverts

### P1

- LAB-OPEN-01 / D1 ;
- ACQ-OPEN-01 / D2 ;
- ACQ-OPEN-02 / D3 ;
- EPI-OPEN-01 / D5 ;
- FHIR-OPEN-01 / D6 ;
- AUTH-OPEN-01 / D7 ;
- RESULT-OPEN-01 / D8 ;
- EQUIP-OPEN-01 ;
- qualification serveur/réseau, sauvegarde/restauration, UAT et worker.

### P2/P3

- AUD-OPEN-01 ;
- FIN-OPEN-01 ;
- EQUIP-OPEN-02 ;
- AUTH-OPEN-03 ;
- AUTH-OPEN-02.

Aucun risque nécessitant une décision humaine n'est fermé par ce dossier.

## 12. Différence entre les niveaux d'autorisation

| Niveau | Ce qu'il autorise | Ce qu'il n'autorise pas |
|---|---|---|
| Fusion technique | Intégrer le SHA revu dans `main`, sans effet runtime | Déploiement, migration réelle, pilote ou activation |
| Pilote préproduction | Préparer un environnement isolé et des tests synthétiques après décision | Patient réel, appareil non commissionné, production |
| Pilote clinique | Utiliser un périmètre clinique signé, limité et supervisé | Généralisation, production ou appareil hors périmètre |
| Production | Exploitation formellement homologuée, surveillée et réversible | Dérogation implicite aux décisions, risques ou commissioning |

Une autorisation de niveau inférieur ne vaut jamais autorisation du niveau
suivant.

## 13. Conditions maintenant le NO-GO

Le NO-GO reste requis tant que manquent notamment :

- qualification réelle des appareils ;
- décisions D1 à D3 pour les interfaces concernées ;
- qualification des référentiels cliniques ;
- infrastructure et réseau réels qualifiés ;
- sauvegarde/restauration répétée sur préproduction ;
- réception synthétique ;
- traitement contrôlé du worker ;
- autorisations humaines signées.

## 14. Décisions indépendantes du comité

### A. Fusion technique de la PR #80 dans `main`, sans déploiement

- [ ] Autorisée pour le SHA : ______________________________
- [ ] Autorisée avec conditions : __________________________
- [ ] Refusée / reportée

Décideurs, justification et date : _________________________________

Cette décision n'autorise ni préproduction, ni pilote, ni déploiement.

### B. Préparation d'une préproduction

- [ ] Autorisée pour le périmètre : _________________________
- [ ] Autorisée avec conditions : __________________________
- [ ] Refusée / reportée

Environnement, responsables, données synthétiques et date : ________________

Cette décision ne vaut ni commissioning, ni pilote clinique.

### C. Commissioning d'un appareil déterminé

- [ ] Autorisé pour l'appareil/profil : ______________________
- [ ] Autorisé avec conditions : ____________________________
- [ ] Refusé / reporté

Identité expurgée, firmware, profil, responsables et date : ________________

Cette décision ne vaut ni activation automatique, ni autorisation de production.

### D. Remise en service du worker d'outbox

- [ ] Autorisée au SHA/release immuable : ___________________
- [ ] Autorisée avec passage unique supervisé : _____________
- [ ] Refusée / reportée

Preuves d'instance unique, compteurs, rollback, responsables et date : ______

Cette décision ne vaut ni fusion de la PR #80, ni pilote clinique.

## 15. Attestations finales

- [ ] Le SHA et la CI ont été relus.
- [ ] Les risques acceptés sont nommés et limités.
- [ ] Les risques ouverts ont un responsable et une échéance.
- [ ] Aucun appareil n'est présenté comme qualifié sans preuve.
- [ ] Le statut du worker a été traité séparément.
- [ ] Les décisions A, B, C et D ont été signées séparément.

Verdict du comité : _______________________________________________<br>
Date : ___________________________________________________________<br>
Autorité clinique : ______________________________________________<br>
Qualité : ________________________________________________________<br>
Exploitation/sécurité : __________________________________________
