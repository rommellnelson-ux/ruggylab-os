# Plan d'amélioration — RuggyLab OS

> À exécuter dans **Claude Code**, ouvert à la racine `ruggylab-os/`, avec le `.venv` actif.
> Chaque lot est autonome : implémenter → lancer les tests → commiter avant de passer au suivant.
> Commandes de référence : `pytest -q` · `ruff check app tests` · `mypy app`

---

## État de départ (déjà fait en revue Cowork)

Trois correctifs de sécurité **déjà appliqués** et à valider en premier :

- `app/services/onmci_client.py` — le repli `FORMAT_ONLY` renvoie désormais `valid=False` (fail closed).
- `app/core/config.py` — `ONMCI_SECRET_KEY` intégré à `requires_security_hardening`.
- `app/api/v1/endpoints/login.py` — détection de réutilisation des refresh tokens (révocation de la famille).
- `tests/test_onmci_client.py` — deux tests réalignés sur le comportement sécurisé.

**Action 0 (bloquante)** : `pytest tests/test_onmci_client.py tests/ -q`. Ne rien faire d'autre tant que la suite n'est pas verte.

---

## Lot 1 — Sécurité : finir le flux ordonnance (priorité 🔴)

**Objectif** : garantir qu'aucune ordonnance non signée n'est acceptée en aval du client ONMCI.

1. Tracer les appelants de `ONMCIClient.verify(...)` :
   `grep -rn "\.verify(" app | grep -i onmci` et `grep -rn "get_onmci_client\|ONMCIVerificationResult" app`.
2. Vérifier que chaque appelant teste **`result.method` en plus de `result.valid`**, et refuse (ou marque « non vérifiée ») tout `method == "FORMAT_ONLY"`.
3. Ajouter un journal d'audit (`log_audit_event`) sur toute vérification d'ordonnance échouée ou en `FORMAT_ONLY`.

**Critères d'acceptation** : un test d'intégration montre qu'un QR non signé (hex aléatoire) est refusé au niveau de l'endpoint prescription, pas seulement du client. Audit émis.

---

## Lot 2 — Durcissement complémentaire (priorité 🟠, rapide)

- `app/main.py:143-145` — désactiver `/docs` et `/openapi.json` hors debug (`docs_url=None` si `not settings.DEBUG`, à ajouter au `Settings`).
- `app/api/v1/endpoints/analyzer.py:20-26` — `_client_ip` : documenter/reprendre la lecture de `X-Forwarded-For` pour prendre le **saut le plus à droite** (le moins spoofable) plutôt que le plus à gauche.
- `app/main.py:45` — s'assurer que le serveur de métriques `:8001` n'est pas exposé publiquement (bind loopback ou note de déploiement/firewall).
- Optionnel : migrer le hachage mot de passe `pbkdf2_sha256` → `argon2` (déjà présent dans passlib), avec `deprecated="auto"` pour re-hacher au login.

**Critères d'acceptation** : tests existants toujours verts ; note de déploiement mise à jour.

---

## Lot 3 — UX : file de synchronisation hors-ligne (priorité 🟠, fort impact terrain)

**Objectif** : rendre le mode dégradé visible et fiable (connectivité intermittente).

1. Exposer un compteur d'éléments en attente de synchronisation (résultats, exports FHIR, outbox de livraison — cf. `report_delivery_outbox.py`).
2. Endpoint `GET /api/v1/sync/status` → `{online: bool, pending: {results, reports, fhir}, last_sync}`.
3. Cockpit : bandeau persistant « Mode hors-ligne — N éléments en attente » + vue liste de la file.

**Critères d'acceptation** : en coupant la connectivité simulée, le bandeau apparaît, le compteur est exact, et la file se vide à la reconnexion. Tests sur l'endpoint de statut.

---

## Lot 4 — UX : résultats critiques + statut « provisoire » (priorité 🟠)

**Objectif** : qu'un résultat dangereux ou non validé soit impossible à mal interpréter.

1. Exploiter `delta_checker` et `reference_checker` pour renvoyer un niveau de criticité par résultat (`critique | hors_bornes | normal | provisoire`).
2. Cockpit : code couleur cohérent (rouge / orange / gris) + tri des résultats critiques en tête.
3. Filigrane « PROVISOIRE — à valider a posteriori » sur les PDF publiés sans validation (`REQUIRE_VALIDATION_FOR_RELEASE=False`), et badge dans les listes.
4. Paludisme positif : action « Notifier le clinicien » en un clic depuis l'alerte.

**Critères d'acceptation** : un résultat en valeur critique et un compte-rendu provisoire sont visuellement distincts ; le PDF provisoire porte le filigrane. Tests sur le calcul du niveau de criticité.

---

## Lot 5 — UX : retour visuel du scan ONMCI + confiance IA paludisme (priorité 🟡)

1. Écran de scan : retour immédiat à 3 états lisibles — vert « signature vérifiée » (`HMAC_LOCAL`/`ONMCI_API`), orange « format seul — non vérifiée » (`FORMAT_ONLY`), rouge « invalide ». S'appuie directement sur le Lot 1.
2. IA paludisme (`malaria_ai`) : afficher le **score de confiance**, ne jamais imposer le classement, permettre la correction du microscopiste en un geste, journaliser la décision humaine finale.

**Critères d'acceptation** : les trois états de scan sont rendus distinctement ; la proposition IA est toujours corrigeable et tracée.

---

## Ordre recommandé

`Lot 0 (valider) → Lot 1 → Lot 2 → Lot 3 → Lot 4 → Lot 5`.
Les lots 1 et 2 ferment la sécurité ; 3 et 4 apportent le gain terrain le plus visible ; 5 est du polish à fort ressenti.

## Rappels transverses

- Un commit par lot, message clair (ex. `fix(onmci): reject unsigned prescriptions at endpoint`).
- Après chaque lot : `pytest -q && ruff check app tests`.
- Garder les libellés d'interface en français (public : personnel du CSA Plateau).
- Ne pas exposer de PII dans les logs/audit (poursuivre le pattern existant : identifiants et noms de champs seulement).
