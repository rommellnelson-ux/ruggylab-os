# Qualification des alertes CodeQL hautes — `main`

- **Date d'analyse** : 2026-08-27
- **Référence analysée** : `refs/heads/main` après fusion des PR #133, #135, #136
- **Règle concernée** : `py/clear-text-logging-sensitive-data` (CWE-312), sévérité *high*
- **Alertes hautes ouvertes au moment du triage** : 8
- **Alertes critiques ouvertes** : 0 (la SSRF `py/full-ssrf` #11 est passée `fixed` après la PR #133)

Ce document existe parce qu'une alerte haute ne peut rester ouverte **que si
elle est formellement analysée, justifiée et suivie**. Aucune alerte n'a été
rejetée pour obtenir un tableau vert.

---

## 1. Tableau de qualification

| N° | Fichier:ligne | Donnée source | Destination | Verdict | Action |
| --- | --- | --- | --- | --- | --- |
| #1 | `app/core/secrets_manager.py:146` | `secret_name` (nom), `exc` (échec Azure) | `logger.error` | **Faux positif démontré** | Aucune — justifié ci-dessous |
| #2 | `app/core/config.py:32` | `secret_name` (nom), `exc` (échec manager) | `logger.warning` | **Faux positif démontré** | Aucune |
| #3 | `app/core/secrets_manager.py:80` | `secret_name` (nom), `exc` (échec AWS) | `logger.error` | **Faux positif démontré** | Aucune |
| #4 | `app/core/secrets_manager.py:188` | `secret_name` (nom), `exc` (échec GCP) | `logger.error` | **Faux positif démontré** | Aucune |
| #5 | `app/core/secrets_manager.py:224` | `manager_type` (`aws`/`azure`/`gcp`) | `logger.info` | **Faux positif démontré** | Aucune |
| #7 | `app/services/billing_engine.py:105` | `patient_type` (catégorie binaire) | `logger.info` | **Risque acceptable documenté** | Aucune — justifié ci-dessous |
| #8 | `app/services/prescription_scanner.py:486` | `patient.age_years` (**âge exact**) | `logger.info` | **Vrai positif** | **Corrigé** — tranche d'âge |
| #10 | `app/api/v1/endpoints/pdf_prescription.py:72` | `prescription_date` via le nom de fichier | `logger.info` | **Vrai positif** | **Corrigé** — champ retiré |

---

## 2. Justification des faux positifs (`core/`, alertes #1 à #5)

Les cinq alertes suivent le même motif. CodeQL considère comme sensible toute
variable dont le nom évoque un secret (`secret_name`) et suit ce marquage
jusqu'au journal. Or ce qui est journalisé est **le nom du secret**, pas sa
valeur :

```python
logger.error("Failed to retrieve secret '%s' from AWS: %s", secret_name, exc)
```

Deux arguments indépendants, chacun suffisant :

1. **La valeur n'est jamais dans l'expression journalisée.** `secret_name` est
   une chaîne comme `"SECRET_KEY"`. Connaître le nom d'un secret n'aide pas à
   l'obtenir ; ce nom figure d'ailleurs déjà en clair dans `.env.example`.

2. **Ces quatre appels sont dans un bloc `except`.** Ils ne s'exécutent que si
   la récupération a **échoué** : à cet instant, aucune valeur de secret
   n'existe dans la portée. L'exception provient du SDK cloud et porte un code
   d'erreur (`AccessDenied`, `ResourceNotFound`) et l'identifiant demandé —
   jamais le contenu, qui n'a pas été renvoyé.

L'alerte #5 (`logger.info("Secrets manager initialized: %s", manager_type)`) ne
journalise qu'un discriminant de configuration valant `aws`, `azure`, `gcp` ou
`local`.

**Suivi.** Ces cinq alertes restent ouvertes et qualifiées. Elles doivent être
réexaminées si le contenu de ces journaux change — la justification porte sur
les expressions actuelles, pas sur les lignes.

---

## 3. Chemins cliniques et financiers — exigence renforcée

Sur ces chemins, aucune tolérance : ni donnée patient brute, ni contenu de
prescription, ni identifiant nominatif, ni montant sensible inutile.

### #8 — `prescription_scanner.py` : âge exact (vrai positif, corrigé)

`patient_age` journalisait l'**âge exact** du patient. Dans la population
restreinte d'un centre de santé, un âge exact horodaté est quasi-identifiant :
croisé avec l'heure du scan, il désigne souvent une seule personne.

Corrigé par `_age_band()`, qui projette l'âge sur un vocabulaire fini
(`0-1`, `2-11`, `12-17`, `18-64`, `65+`, `inconnu`). Les règles d'interaction et
de posologie dépendent du **groupe** d'âge : la valeur diagnostique du journal
est conservée, l'attribut patient disparaît.

### #10 — `pdf_prescription.py` : date d'ordonnance (vrai positif, corrigé)

Le champ `pdf_filename` valait `ordonnance-<date>.pdf`, où la date provenait du
dossier du patient. Elle n'apportait rien : seuls comptent le verdict du scan et
sa confiance. Le champ est remplacé par `pdf_bytes` (taille du document), qui
permet de repérer une génération anormale sans rien révéler du contenu.

### #7 — `billing_engine.py` : type de patient (risque acceptable, documenté)

`patient_type` est une **catégorie administrative fermée** (assuré / non
assuré), pas une donnée nominative ni un attribut clinique. C'est aussi la
variable qui détermine le sous-moteur de facturation appelé : la retirer
supprimerait la seule information permettant de diagnostiquer une facturation
erronée, sans gain de confidentialité réel — un booléen à deux valeurs
n'identifie personne.

**Conservée, qualifiée « risque acceptable ».** À revoir si ce journal venait à
porter un montant, un identifiant de patient ou un libellé de diagnostic.

---

## 4. Verrouillage par les tests

`tests/test_no_patient_attributes_in_logs.py` empêche la régression :

- la tranche d'âge ne restitue jamais l'âge exact, et sa sortie appartient à un
  vocabulaire fini ;
- le journal réellement émis par `PrescriptionScanner.scan` est inspecté, et
  l'absence d'une liste d'attributs interdits (`patient_age`, `patient_id`,
  `ipp`, `birth_date`, `pdf_filename`, `prescription_date`…) est vérifiée ;
- l'âge exact injecté dans le test n'apparaît dans aucune valeur journalisée.

---

## 5. État visé et état réel

| Objectif | État |
| --- | --- |
| `0_CRITICAL_OPEN` | ✅ atteint — SSRF #11 `fixed` |
| `0_HIGH_UNQUALIFIED` | ✅ atteint après fusion de cette PR — 2 corrigées, 6 qualifiées ici |

Les alertes qualifiées **restent ouvertes** dans GitHub : aucune n'a été
rejetée. Ce document est leur suivi.
