# G0 — Schéma PostgreSQL et graphe des migrations

> **INTERNAL — SECURITY ARCHITECTURE**
> **BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT**
>
> Ce document décrit une architecture de référence, pas une installation. Il ne
> contient aucune adresse IP réelle de site, aucun identifiant, aucun secret,
> aucun nom de compte, aucune topologie VLAN réelle et aucune donnée patient —
> et il ne doit pas en recevoir tant que le dépôt reste public.
>
> Ce bandeau est une **mention de classification, pas un contrôle d'accès** : il
> n'empêche personne de lire ce fichier. Le seul contrôle réel serait la
> visibilité du dépôt.

> **Introspecté sur une base réellement migrée**, jamais lu dans les modèles
> Python. Les deux peuvent diverger — une migration écrite à la main, un
> `server_default` oublié, un index créé hors modèle. Décrire les modèles
> reviendrait à décrire ce qu'on croit avoir.
>
> Généré par
> [`scripts/g0_schema_inventory.py`](../../scripts/g0_schema_inventory.py).
> Provenance : [`artifacts/g0/schema-provenance.json`](../../artifacts/g0/schema-provenance.json)

## 1. Environnement de mesure

| | |
| --- | --- |
| Serveur | **PostgreSQL 16.14** (`postgres:16-alpine`, conteneur jetable) |
| Base | `g0_baseline`, créée vide |
| Migration appliquée | `alembic upgrade head` **avant** introspection |
| Données | **aucune** — le catalogue est interrogé, pas les tables |

> Migrer et introspecter dans le même processus masquerait une migration qui
> échoue partiellement. Les deux étapes sont séparées, et la CI les enchaîne
> explicitement.

## 2. Objets du schéma `public`

| Objet | Nombre |
| --- | --- |
| Schémas | 1 |
| **Tables** | **49** |
| Colonnes | **519** |
| Clés primaires | 49 |
| **Clés étrangères** | **56** |
| Contraintes UNIQUE | 26 |
| Contraintes CHECK | 3 |
| **Index** | **170** |
| Séquences | 48 |
| Types enum | 1 |
| Extensions | 1 (`plpgsql` 1.0) |
| Vues | **0** |
| Vues matérialisées | **0** |
| Fonctions | **0** |
| Triggers | **0** |
| **Politiques RLS** | **0** |

Chaque table a exactement une clé primaire — 49 pour 49.

### Le seul enum

```
userrole → technician, officer, admin, accountant
```

Quatre rôles, cohérents avec `UserRole` dans le code. Le lot B croisera ces
quatre valeurs avec les 231 opérations d'API.

### Les trois contraintes CHECK

Toutes sur le registre d'équipements : `ck_equipment_interfaces_direction`,
`ck_equipment_interfaces_type`, `ck_equipment_qualifications_status`.

> **Trois CHECK pour 519 colonnes.** L'essentiel de la validation vit donc dans
> l'application, pas dans la base. Ce n'est pas anormal pour une application
> Python typée, mais cela signifie qu'une écriture directe en base — import,
> correction manuelle, script — contournerait la validation. Constat transmis
> au lot D.

## 3. Relations

Les tables les plus référencées :

| Table | Clés étrangères entrantes |
| --- | --- |
| `users` | **21** |
| `results` | 6 |
| `equipments` | 6 |
| `patients` | 4 |
| `reagents` | 3 |

`users` est le pivot d'auditabilité : 21 tables portent une référence vers
l'auteur d'une action. C'est cohérent avec l'exigence d'identifier l'auteur de
chaque opération.

### Comportement à la suppression

| Règle | Clés étrangères |
| --- | --- |
| `NO ACTION` | **50** |
| `RESTRICT` | 6 |

**Aucun `CASCADE`.** Rien ne s'efface en chaîne : supprimer un patient
référencé échoue plutôt que d'emporter ses résultats. Pour un système clinique
tenu à la traçabilité, c'est le comportement souhaitable — et il est ici
constaté, pas supposé.

### Onze tables isolées

Onze tables n'ont ni clé étrangère entrante ni sortante :
`alembic_version`, `auto_validation_configs`, `biological_code_mappings`,
`biological_reference_ranges`, `critical_ranges`, `csa_sync_state`,
`delta_check_rules`, `exam_tariffs`, et trois autres — voir
[`artifacts/g0/schema.json`](../../artifacts/g0/schema.json).

Ce sont des tables de **référentiel** ou d'**état** : catalogues, seuils,
tarifs, état de synchronisation. Leur isolement est attendu. `alembic_version`
est la table technique d'Alembic.

## 4. Graphe des migrations

| | |
| --- | --- |
| Révisions | **43** |
| **Têtes** | **1** — `20260826_0043` |
| Tête attendue | `20260826_0043` ✅ |
| Points de fusion | **aucun** |
| Points de branche | **aucun** |

**Une seule tête, aucune branche, aucune fusion** : la chaîne est linéaire.
C'est le cas le plus sain — deux têtes rendraient `upgrade head` ambigu, et une
partie du schéma pourrait n'être jamais appliquée sans que rien ne le signale.

Le script **échoue** si le nombre de têtes n'est pas 1, ou si la tête diffère
de celle attendue. Il ne modifie aucune migration pour y parvenir : un écart
est un fait à expliquer.

L'ordre topologique complet est dans
[`artifacts/g0/alembic-graph.json`](../../artifacts/g0/alembic-graph.json).

## 5. Ce que ce schéma ne dit pas

- **Aucun privilège restrictif n'est constaté.** Les 49 entrées de
  `table_privileges` correspondent au propriétaire. L'application se connecte
  avec un rôle unique ; aucune séparation de privilèges au niveau base.
- **Aucune politique RLS.** Le cloisonnement — comptable sans accès patients,
  notamment — est appliqué dans l'application. Le lot B devra dire si cela
  suffit ; le constater ici ne le valide pas.
- **Le contenu des tables n'a pas été lu.** Seul le catalogue a été interrogé.

## 6. Constats transmis au lot D

| Constat | Classement |
| --- | --- |
| Aucune politique RLS : le cloisonnement repose entièrement sur l'application | **P1** |
| 3 contraintes CHECK pour 519 colonnes : une écriture directe contournerait la validation | **P2** |
| Rôle base unique, sans séparation de privilèges | **P2** |
| Aucun `CASCADE` — *constat favorable*, à préserver | — |
