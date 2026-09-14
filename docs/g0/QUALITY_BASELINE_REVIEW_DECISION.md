# G0 — Décision de revue sur la baseline de qualité (lot C)

> **INTERNAL — SECURITY ARCHITECTURE**
> **BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT**
>
> Ce document consigne une décision de gouvernance, pas une installation. Il ne
> contient aucune adresse IP réelle de site, aucun identifiant, aucun secret,
> aucune donnée patient. Ce bandeau est une **mention de classification, pas un
> contrôle d'accès**.

```
G0_LOT_C_INDEPENDENT_REVIEW = ACCEPTED
QUALITY_BASELINE_ACCEPTED
review_date_utc             = 2026-09-13
```

## 1. Sur quoi porte l'acceptation

Sur la **validité de la preuve**, et sur rien d'autre : la campagne de mesure
dit ce qu'elle prétend dire, sur le code qu'elle prétend décrire, avec de quoi
la rejouer et la contredire.

Concrètement, la revue a établi que :

- la mesure de couverture lignes et branches est techniquement valide ;
- la mesure de performance est techniquement valide ;
- les identités de la campagne sont enregistrées séparément et sans confusion ;
- la version du serveur Valkey publiée est celle du **produit** (8.1.9), et non
  sa compatibilité de protocole (7.2.4) ;
- aucune causalité non démontrée n'est présentée comme mesurée ;
- le décompte des jobs de CI est **généré**, jamais saisi.

La campagne archivée est identifiée par son commit source :

```
measurement_source_sha = 02795a81b801b784572089d6a7860ba889d10a4c
snapshot               = artifacts/g0/accepted/quality/02795a81b801b784572089d6a7860ba889d10a4c/
```

## 2. Sur quoi elle ne porte pas

> **Accepter une preuve n'est pas accepter un produit.** Ce sont deux décisions
> différentes, prises sur des critères différents, et les confondre est
> précisément ce que cette campagne existe pour empêcher.

```
G0_PASS            = NON
REAL_DATA_GO       = NON
SITE_PRODUCTION_GO = NON
DISTRIBUTION_GO    = NON
```

RuggyLab OS **n'est pas accepté pour la production clinique**. Les statuts de
gouvernance restent inchangés :

```
CLINICAL_STATUS     = REAL_DATA_NO_GO
DISTRIBUTION_STATUS = DISTRIBUTION_NO_GO
CSA_SYNC_ENABLED    = false
ENABLE_DH36_LISTENER = false
ANALYZER_RAW_LISTENER_ENABLED = false
```

## 3. Aucun seuil n'a été imposé, et c'est délibéré

G0 **constate**. La revue n'a fixé :

- **aucun seuil de couverture** — 51,97 % de lignes et 12,89 % de branches sont
  publiés tels qu'ils sortent de la mesure, sans être déclarés suffisants ni
  insuffisants ;
- **aucun objectif de latence** — les p50, p95 et p99 sont des observations ;
- **aucun seuil de CPU ou de mémoire** — une consommation élevée est un
  résultat ; c'est l'**absence** de mesure qui invalide une campagne.

Un seuil se contourne en choisissant ses tests ou son moment de mesure. Une
baseline qui en porterait un cesserait d'être une observation pour devenir un
verdict, et le verdict finirait par être négocié.

## 4. Ce qui reste ouvert

L'acceptation de la preuve **ne referme aucun de ces constats**. Ils sont
inscrits dans `EVIDENCE_MANIFEST.json` (`open_findings`), chacun avec la ligne
d'artefact qui l'étaye, et sont transmis au lot D.

| Constat | Gravité | Ce qui est mesuré |
| --- | :-: | --- |
| **`CSA_SITE_PRODUCTION_GO_BLOCKER`** | P1 | `invoice_create` répond HTTP 500 **dès trois utilisateurs simultanés** — le premier usage envisagé au CSA GR Plateau. 6 échecs sur 45. |
| **`INVOICE_CONCURRENCY_REMEDIATION_REQUIRED`** | P1 | Le taux d'échec croît avec la concurrence : 13 % à trois, 17 % à cinq, 28 % à dix. Aucun réessai. |
| **`PERFORMANCE_BOTTLENECK_PROFILING_REQUIRED`** | P1 | Plateau de CPU applicatif **concomitant** à la dégradation des latences. La cause n'est pas établie : contention transactionnelle, verrou, sérialisation, pool de connexions, GIL ou file interne ne sont pas exclus. |
| **`SITE_OPERATIONAL_PROFILE_REQUIRED`** | P1 | La campagne mesure le cœur **limiteurs désactivés**. Le comportement du site reste à mesurer. |
| `AUTH_CONCURRENCY_INVESTIGATION_REQUIRED` | P2 | HTTP 502 sur l'authentification à concurrence 10 (3/150). Intermittent d'une campagne à l'autre. |

> **Le blocage de facturation est le plus lourd de conséquence.** Dans une
> facturation clinique, un `500` n'est pas une gêne d'affichage : l'acte a-t-il
> été facturé ou non ? La question se pose pour chaque occurrence, et le pas
> suivant du parcours s'en trouve amputé — `payment_create` n'a recueilli que
> 39 encaissements sur 45 tentatives à trois utilisateurs.
>
> Il n'est **pas corrigé** par cette PR, et ce n'est pas un oubli : corriger un
> défaut découvert en le mesurant reviendrait à publier la mesure d'un système
> qu'on vient de changer.

## 5. Avant tout pilote réel

Une campagne distincte reste **obligatoire**, avec :

- les deux limiteurs de débit **actifs** ;
- Caddy en position réelle de terminaison TLS ;
- un `X-Forwarded-For` réel et `TRUSTED_PROXY_IPS` configuré pour le site ;
- trois clients représentatifs sur trois adresses distinctes ;
- la protection anti-force-brute active ;
- la vérification qu'aucun `429` ne survient pendant un parcours normal.

Elle **n'a pas été exécutée**. Aucune phrase de ce document ne doit être lue
comme si elle l'avait été.

## 6. Forme de la décision

La décision est consignée comme un **fait de gouvernance**. Aucune signature
n'est apposée ni simulée, et ce document n'en tient pas lieu.

La preuve elle-même est vérifiable sans faire confiance à ce document :
`artifacts/g0/accepted/quality/02795a81b801b784572089d6a7860ba889d10a4c/README.md`
explique comment recalculer les cinq empreintes et retrouver l'exécution qui les
a produites.
