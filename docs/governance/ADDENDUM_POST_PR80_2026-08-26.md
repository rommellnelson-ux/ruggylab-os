# Addendum de gouvernance post-PR #80 — RuggyLab OS

> **PROJET DE DÉCISION — À VALIDER ET SIGNER**
>
> Ce document n'est **pas** une décision. Il constate des faits vérifiables et
> propose un texte à valider. Aucune signature n'y est simulée ni pré-remplie.
> Tant qu'il n'est pas signé, la doctrine antérieure s'applique intégralement.

- **Date de rédaction** : 2026-08-26 (date réelle de rédaction).
- **Rédacteur** : revue technique de réintégration (Lead Software Engineer /
  DevSecOps), sans autorité clinique.
- **Portée** : constater l'état de gouvernance après la fusion de la PR #80 et
  encadrer les intégrations techniques en cours (CSA I1/I2/I4, réseau automates).
- **Ne modifie ni ne remplace** :
  [`GO_NO_GO_RUGGYLAB_2026.md`](../GO_NO_GO_RUGGYLAB_2026.md),
  [`GO_NO_GO_COMMITTEE_PACK_2026.md`](../GO_NO_GO_COMMITTEE_PACK_2026.md),
  [`PR80_MAIN_INTEGRATION_REVIEW_2026.md`](../PR80_MAIN_INTEGRATION_REVIEW_2026.md).
  Ces documents restent en vigueur tels qu'écrits ; **aucun n'est modifié
  rétroactivement ni antidaté**.

---

## 1. Faits constatés

Chaque fait ci-dessous est vérifiable par une commande Git, l'API GitHub ou un
fichier du dépôt. Aucun n'est déduit ni supposé.

| # | Fait | Preuve |
| --- | --- | --- |
| F1 | La PR #80 a été **fusionnée le 2026-08-04 à 16:25:05 UTC**, par commit de fusion `65e1a02be60408d32d3de8a838fafebd2e8a3603`. | `gh pr view 80 --json mergedAt,mergeCommit` |
| F2 | Cette fusion est une **intégration technique de code**. Elle n'emporte, par elle-même, aucune autorisation clinique ni de déploiement. | Nature de l'opération Git ; §1 de `PR80_MAIN_INTEGRATION_REVIEW_2026.md`. |
| F3 | Le bloc « Décision de comité » de `GO_NO_GO_RUGGYLAB_2026.md` est **intégralement vierge** : les trois cases (GO fusion technique / GO AVEC CONDITIONS / NO-GO) sont non cochées, et les champs Décision, SHA autorisé, Run CI, Risques acceptés, Autorité clinique, Exploitation/sécurité/qualité et Date sont vides. | `GO_NO_GO_RUGGYLAB_2026.md`, section « Décision de comité ». |
| F4 | Plusieurs critères de passage au GO restent **non cochés**, dont : revue humaine de #107 et du dossier appareil ; CI verte sur le SHA incluant le dossier documentaire ; méthode de fusion ; absence de déploiement déclenché ; rollback applicatif préparé ; suivi D1–D8. | `GO_NO_GO_RUGGYLAB_2026.md`, section « Critères de passage au GO AVEC CONDITIONS ». |
| F5 | **Aucune décision formelle de levée du NO-GO n'a été retrouvée** dans le dépôt, ni avant ni après le 2026-08-04. | Recherche sur `docs/` ; voir F6. |
| F6 | Depuis la fusion de la PR #80, **une seule PR a été fusionnée dans `main`** : la PR #133 (correctif de sécurité SSRF), le 2026-08-26. Aucune PR de gouvernance n'est intervenue entre les deux. | `gh pr list --state merged --base main` ; `git log 65e1a02..origin/main` |
| F7 | Le verdict écrit des deux dossiers reste **« NO-GO »** et **« parc NON ACTIVABLE EN CLINIQUE »**. | `GO_NO_GO_RUGGYLAB_2026.md` §« Verdict préparatoire » ; `PR80_MAIN_INTEGRATION_REVIEW_2026.md` §1. |
| F8 | `REQUIRE_VALIDATION_FOR_RELEASE` vaut **`False` par défaut** dans le code, et le dossier consigne ce mode comme « à renverser dès affectation d'un biologiste validateur ». | `app/core/config.py` ; `GO_NO_GO_RUGGYLAB_2026.md`, tableau des contrôles compensatoires. |
| F9 | Dans `docker-compose.yml`, la passerelle automates est **inerte** : listeners `false`, aucun port publié, commentaire « interfaces désactivées jusqu'à qualification ». | `docker-compose.yml`, service `analyzer-gateway`. |
| F10 | La vulnérabilité SSRF critique (CodeQL `py/full-ssrf`, alerte #11) est **corrigée et vérifiée fermée** sur `main` le 2026-08-26 à 16:24:20 UTC. | Alerte #11 `state: fixed` ; run CI `32987425070` vert sur `main`. |

### 1.1 Lecture de ces faits

F1 + F3 + F5 + F6 établissent ensemble le point central : **la PR #80 a été
fusionnée sans que la décision de comité prévue par son propre dossier ait été
renseignée.** Il ne s'agit pas de contester la fusion — elle est technique, et
l'état du code a par ailleurs progressé — mais de constater qu'**aucun acte
formel n'a levé le NO-GO**, et qu'aucun n'est intervenu depuis.

En l'absence d'acte contraire, la doctrine écrite continue de s'appliquer.

---

## 2. Texte proposé à la décision

> Les points 1 à 10 constituent le texte soumis à validation et signature.

1. La fusion de la PR #80, le 2026-08-04, est reconnue comme une **intégration
   technique de code dans `main`**.
2. Cette fusion **n'a pas emporté** de levée du NO-GO clinique ou opérationnel,
   le bloc de décision de comité étant demeuré vierge.
3. Le statut clinique et opérationnel demeure : **`REAL_DATA_NO_GO`**.
4. Les essais autorisés se font **exclusivement sur données fictives ou
   synthétiques**. Aucune donnée patient réelle n'est admise, ni en base de
   développement, ni en jeu de tests, ni en environnement de démonstration.
5. Le **parc d'automates n'est pas activable en clinique** sans qualification
   documentée, appareil par appareil. La stack par défaut n'ouvre et ne publie
   aucun port automate (F9) ; toute activation passe par un override explicite,
   qualifié et propre au site.
6. `REQUIRE_VALIDATION_FOR_RELEASE=false` désigne un **mode dégradé**. Il
   **n'est en aucun cas assimilable à une validation biologique**. Tout
   résultat libéré dans ce mode doit être identifié comme tel de bout en bout,
   y compris auprès de tout système tiers destinataire.
7. Le **lien ordre ↔ résultat par recherche différée** demeure une limite
   d'architecture. Elle est encadrée — et non supprimée — par les garde-fous de
   cohérence patient posés au point de publication (§3.2).
8. La fusion de la PR d'intégration CSA (flux I1/I2/I4 et file de travail)
   **n'emporte aucune autorisation de production ni de mise en service
   clinique**. Elle autorise l'intégration technique et les essais sur données
   fictives.
9. La fusion de la PR de restriction réseau des automates **n'active aucun
   automate** : elle restreint et valide une capacité déjà présente.
10. La levée du NO-GO ne peut résulter que d'une **décision formelle, datée et
    signée** par les autorités désignées au §4, après satisfaction des critères
    du §5.

---

## 3. Éléments techniques nouveaux portés à la connaissance du comité

Ces éléments sont postérieurs aux dossiers existants et éclairent la décision.
Ils ne la préjugent pas.

### 3.1 Sécurité — SSRF critique corrigée

La seule alerte de sévérité **critique** ouverte sur `main` (CodeQL
`py/full-ssrf`, webhooks sortants) est corrigée et vérifiée fermée (F10). Le
transport HTTP sortant est centralisé, valide toutes les réponses DNS, épingle
la connexion à l'adresse validée, refuse les redirections et impose un plancher
TLS 1.2.

**Restent ouvertes sur `main`** : 0 critique, 7 hautes
(`py/clear-text-logging-sensitive-data`) et 5 moyennes
(`py/stack-trace-exposure`). Ces alertes hautes **ne sont pas encore
qualifiées** : elles doivent être analysées et tranchées avant tout GO (§5).

### 3.2 Cohérence patient au point de publication externe

Le flux sortant CSA publie un résultat **sous une identité patient, chez un
tiers**. Deux défauts ont été identifiés et corrigés dans la PR d'intégration :

- la publication ne vérifiait pas que l'échantillon d'origine du résultat
  appartenait bien au patient de l'ordre. Un garde-fou *fail-closed* bloque
  désormais toute publication incohérente et journalise l'incident (sans donnée
  nominative). La non-vacuité du contrôle est démontrée : neutralisé, le
  résultat inter-patients **est** publié ;
- le message sortant annonçait `statut: "valide"` pour **tout** résultat, y
  compris un résultat seulement *libéré* sans validation biologique — c'est-à-
  dire précisément le mode dégradé du point 6. Le niveau réel
  (`biologique` / `auto` / `aucune`) est désormais transmis explicitement.

Le second point est une **illustration concrète du risque** que le point 6
entend prévenir : un mode dégradé peut se présenter comme une validation
biologique sans qu'aucune décision ne l'ait voulu.

### 3.3 Réseau automates

Le mécanisme de publication des ports automates est borné à une interface
nommée (`ANALYZER_BIND_IP`), avec refus au démarrage d'un bind universel, d'un
nom d'hôte ou d'une adresse publique. **La stack par défaut reste inerte.**

---

## 4. Signataires requis

Aucune de ces lignes ne doit être pré-remplie. Le document n'est valide que
signé par l'ensemble des autorités ci-dessous.

| Rôle | Nom | Date | Signature |
| --- | --- | --- | --- |
| Autorité clinique (biologiste responsable) | | | |
| Responsable qualité | | | |
| Responsable exploitation / sécurité | | | |
| Responsable médical de la structure | | | |

Décision retenue (cocher une seule case) :

- [ ] Addendum **adopté** : `REAL_DATA_NO_GO` confirmé, intégrations techniques
      autorisées sur données fictives.
- [ ] Addendum **adopté avec réserves** : ______________________________________
- [ ] Addendum **rejeté** / à réécrire : _______________________________________

---

## 5. Conditions cumulatives d'une future levée du NO-GO

Toutes doivent être satisfaites et **prouvées**. Aucune n'est présumée acquise.

| # | Condition | Preuve attendue | Statut au 2026-08-26 |
| --- | --- | --- | --- |
| C1 | Aucune alerte de sécurité **critique** ouverte | Tableau CodeQL sur `main` | ✅ **satisfait** (0 critique) |
| C2 | Alertes **hautes** qualifiées (corrigées ou justifiées et suivies) | Analyse écrite par alerte | ❌ 7 hautes non qualifiées |
| C3 | CI **entièrement verte** sur le SHA autorisé | Run GitHub Actions | ✅ run `32987425070` vert sur `main` |
| C4 | **Tête Alembic unique** | `alembic heads` | ⏳ à revérifier sur le SHA autorisé |
| C5 | Test de **sauvegarde et de restauration** réussi | Procès-verbal de restauration | ❌ à produire |
| C6 | Qualification d'**au moins un automate physique** | Dossier de commissioning signé | ❌ à produire |
| C7 | **Cohérence patient** démontrée | Tests + revue | ⏳ démontrée sur le flux CSA (§3.2) ; à étendre à l'ensemble des flux |
| C8 | Règles de **validation et de libération** approuvées | Matrice signée | ❌ à produire |
| C9 | Gestion des **valeurs critiques** approuvée | Procédure signée | ❌ à produire |
| C10 | Procédure de **correction des résultats** approuvée | Procédure signée | ❌ à produire |
| C11 | **Journalisation et audit** vérifiés | Revue d'audit datée | ❌ à produire |
| C12 | **Pilote limité, réversible et supervisé** défini | Protocole de pilote signé | ❌ à produire |
| C13 | **Responsables et signataires** identifiés | §4 du présent document | ⏳ à renseigner |

Légende : ✅ satisfait et prouvé — ⏳ partiel ou à revérifier — ❌ non satisfait.

**Au 2026-08-26, les conditions ne sont pas réunies. Le statut demeure
`REAL_DATA_NO_GO`.**

---

## 6. Ce que ce document ne fait pas

- Il **ne lève pas** le NO-GO et n'en propose pas la levée.
- Il **ne déclare aucun GO** clinique, opérationnel ou de production.
- Il **ne modifie ni n'antidate** aucun document de décision antérieur.
- Il **ne simule aucune signature** et n'engage aucun signataire.
- Il **ne qualifie aucun automate** et n'autorise aucune donnée réelle.
