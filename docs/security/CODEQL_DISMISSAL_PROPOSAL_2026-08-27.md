# Dossier de décision — rejet proposé d'alertes CodeQL

> **AUCUN REJET N'A ÉTÉ EXÉCUTÉ.** Ce document propose des rejets à une décision
> humaine. Les six alertes concernées **restent ouvertes** dans GitHub tant
> qu'une autorisation distincte n'est pas donnée.

- **Date d'analyse** : 2026-08-27
- **Référence** : `refs/heads/main`
- **Analyse détaillée** : `CODEQL_HIGH_TRIAGE_2026-08-27.md`

## Pourquoi ce document

Laisser six alertes hautes ouvertes indéfiniment finit par banaliser le tableau
de bord : on cesse de le lire, et une vraie alerte s'y perd. Les rejeter sans
justification écrite serait pire. Ce dossier propose donc, pour chacune, un
motif GitHub et un commentaire de rejet, à valider par une personne.

Le rejet n'est **pas** obligatoire : une alerte formellement analysée, justifiée
et suivie peut rester ouverte. C'est l'état actuel, et il est acceptable.

## Ce qui n'est pas proposé au rejet

Les quatre alertes moyennes `py/stack-trace-exposure` (#6, #14, #15, #16) sont
**corrigées** dans la PR « security(errors): stop exposing internal detail in
error responses », pas rejetées. Elles se fermeront d'elles-mêmes.

---

## Proposition 1 — alertes #1 à #5 : `false positive`

**Motif GitHub proposé** : `False positive`

| N° | Fichier | Expression analysée |
| --- | --- | --- |
| #1 | `app/core/secrets_manager.py:146` | `logger.error("Failed to retrieve secret '%s' from Azure Key Vault: %s", secret_name, exc)` |
| #2 | `app/core/config.py:33` | `logger.warning("Failed to load secret '%s' from cloud manager: %s. Using default.", secret_name, exc)` |
| #3 | `app/core/secrets_manager.py:80` | `logger.error("Failed to retrieve secret '%s' from AWS: %s", secret_name, exc)` |
| #4 | `app/core/secrets_manager.py:188` | `logger.error("Failed to retrieve secret '%s' from GCP: %s", secret_name, exc)` |
| #5 | `app/core/secrets_manager.py:224` | `logger.info("Secrets manager initialized: %s", manager_type)` |

**Justification.** CodeQL marque comme sensible toute variable dont le nom évoque
un secret, puis suit ce marquage jusqu'au journal. Or ce qui est journalisé ici
est le **nom** du secret (`"SECRET_KEY"`), jamais sa valeur. Deux arguments,
chacun suffisant :

1. La valeur n'apparaît dans aucune des expressions ci-dessus.
2. #1 à #4 sont dans un bloc `except` : ils ne s'exécutent **que si la
   récupération a échoué**. À cet instant, aucune valeur de secret n'existe dans
   la portée — il n'y a rien à divulguer. L'exception provient du SDK cloud et
   porte un code d'erreur (`AccessDenied`, `ResourceNotFound`).

#5 ne journalise qu'un discriminant de configuration valant `aws`, `azure`,
`gcp` ou `local`.

**Commentaire de rejet proposé** *(identique pour #1 à #4)* :

> Faux positif : l'expression journalise le NOM du secret, jamais sa valeur.
> L'appel est dans un bloc `except` et ne s'exécute que si la récupération a
> échoué — aucune valeur de secret n'existe alors dans la portée. Analyse :
> docs/security/CODEQL_HIGH_TRIAGE_2026-08-27.md §2. Réexamen : 2027-02-27.

**Commentaire de rejet proposé** *(#5)* :

> Faux positif : `manager_type` est un discriminant de configuration
> (`aws`/`azure`/`gcp`/`local`), pas un secret. Analyse :
> docs/security/CODEQL_HIGH_TRIAGE_2026-08-27.md §2. Réexamen : 2027-02-27.

**Date de réexamen** : 2027-02-27, ou immédiatement si le contenu de ces
journaux change — la justification porte sur les expressions, pas sur les lignes.

---

## Proposition 2 — alerte #7 : `won't fix`

**Motif GitHub proposé** : `Won't fix` *(et non `False positive` : le champ est
bien un attribut de patient — c'est le risque qui est jugé acceptable, pas
l'alerte qui est jugée fausse)*

| N° | Fichier | Expression analysée |
| --- | --- | --- |
| #7 | `app/services/billing_engine.py:105` | `logger.info("billing.process", extra={"patient_type": request.patient_type, "drug_count": …, "diagnosis_count": …, "payment_method": …})` |

**Justification.** `patient_type` est une catégorie administrative fermée
(assuré / non assuré) : ni nominative, ni clinique. Un booléen à deux valeurs
n'identifie personne. C'est aussi la variable qui détermine quel sous-moteur de
facturation est appelé : la retirer supprimerait le seul élément permettant de
diagnostiquer une facturation erronée, sans gain réel de confidentialité.

Contrairement à `patient_age` (#8, corrigé), il n'existe pas de granularité
intermédiaire à laquelle se replier : la valeur est déjà au minimum.

**Commentaire de rejet proposé** :

> Risque acceptable documenté. `patient_type` est une catégorie administrative
> fermée (assuré / non assuré), ni nominative ni clinique, et détermine le
> sous-moteur de facturation appelé — indispensable au diagnostic d'une
> facturation erronée. Analyse :
> docs/security/CODEQL_HIGH_TRIAGE_2026-08-27.md §3. À rouvrir si ce journal
> vient à porter un montant, un identifiant de patient ou un libellé de
> diagnostic. Réexamen : 2027-02-27.

**Date de réexamen** : 2027-02-27, ou immédiatement si le contenu de ce journal
change.

---

## Si la décision est de rejeter

Les rejets s'exécutent alerte par alerte, avec le motif et le commentaire
ci-dessus. Ils sont **réversibles** : une alerte rejetée peut être rouverte, et
elle l'est automatiquement si CodeQL la détecte à nouveau après modification du
code concerné.

## Si la décision est de ne pas rejeter

Rien à faire : l'état actuel est déjà conforme. Les six alertes restent ouvertes,
analysées, justifiées et suivies par le document de triage — ce qui satisfait la
règle « aucune alerte haute non qualifiée ».
