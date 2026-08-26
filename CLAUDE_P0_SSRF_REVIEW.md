# CLAUDE_P0_SSRF_REVIEW

**Revue de sécurité applicative indépendante — correctif P0 SSRF**
Périmètre : `app/services/notifier.py`, `tests/test_stock_notifications.py` (+ garde réutilisé `app/utils/url_safety.py`)
Branche : `feat/acquisition-3-flux` · worktree non modifié · Python 3.13.13
Exclus du périmètre : `.env.example`, `docker-compose.yml`, `PLAN_AMELIORATION.md`

---

## A. Verdict

### PARTIAL

Le garde est correctement **appelé avant tout accès réseau**, et sa couverture des **IP littérales** est solide (loopback v4/v6, RFC 1918, link-local, métadonnées cloud, IPv4-mapped IPv6, encodages IPv4 alternatifs, userinfo, schémas non-HTTP, alias `localhost`, ports arbitraires — tous bloqués, matrice empirique en §D).

Cependant **la primitive réseau reste atteignable sur le réseau interne** par deux chemins confirmés par PoC exécutés :

1. **Redirection HTTP 302** — le garde n'est appliqué qu'à l'URL initiale ; `urllib.request.urlopen` suit les redirections avec l'opener par défaut, sans re-validation de chaque saut. **PoC : service interne atteint.**
2. **TOCTOU / DNS rebinding** — le garde résout le nom, puis `urlopen` le résout **une seconde fois, indépendamment**. **PoC : POST livré au service interne.**

Le correctif est un **gain net réel et sans régression** (il bloque l'exploitation directe et triviale), mais il **ne ferme pas le P0**.

---

## B. Attack surface

### Chemin complet request → appel réseau

| # | Étape | Emplacement | Contrôle attaquant |
|---|-------|-------------|--------------------|
| 1 | `POST /api/v1/stock/notify` | [stock_notifications.py:26-41](app/api/v1/endpoints/stock_notifications.py:26) | corps JSON |
| 2 | AuthN/AuthZ | `Depends(get_current_active_user)` — [deps.py:67](app/api/deps.py:67) | **tout utilisateur actif authentifié, quel que soit son rôle** |
| 3 | Validation Pydantic | `NotificationRequest.webhook_url: str \| None` — [notification.py:83](app/schemas/notification.py:83) | **aucune** (type `str` brut, pas `AnyHttpUrl`, pas de `max_length`) |
| 4 | Aiguillage canal | [notifier.py:113-115](app/services/notifier.py:113) | `channel` ∈ {WEBHOOK, BOTH} |
| 5 | **Garde SSRF** | [notifier.py:148](app/services/notifier.py:148) — `if not is_safe_external_url(url)` | — |
| 6 | Résolution DNS n°1 (garde) | [url_safety.py:61](app/utils/url_safety.py:61) — `socket.getaddrinfo(host, None)` | via son propre DNS |
| 7 | Construction requête | [notifier.py:153-161](app/services/notifier.py:153) | méthode POST, corps JSON serveur |
| 8 | **Résolution DNS n°2 (connexion)** | `http.client` → `socket.create_connection` | via son propre DNS — **fenêtre TOCTOU** |
| 9 | **Appel réseau** | [notifier.py:163](app/services/notifier.py:163) — `urllib.request.urlopen(req, timeout=…)` | opener par défaut |
| 10 | **Sauts de redirection** | `HTTPRedirectHandler` (opener par défaut) | **en-tête `Location` contrôlé par l'attaquant, non re-validé** |
| 11 | Retour d'information | [notifier.py:115-120](app/services/notifier.py:115) → `notifications_sent`, `errors[]` | oracle 2xx / non-2xx |

### Deuxième chemin vers la même primitive

`POST /api/v1/critical-alerts/config` ([critical_alerts.py:57-64](app/api/v1/endpoints/critical_alerts.py:57)) permet de **persister** un `webhook_url` arbitraire en base (`NotifConfig`), consommé ensuite par `critical_notifier` et `expiry_notifier`. Ce chemin est protégé par `require_officer` (officer/admin) — donc plus restrictif que `/stock/notify`.

---

## C. Correctif observé

Diff exact (3 lignes utiles) :

```diff
+from app.utils.url_safety import is_safe_external_url

     def _send_webhook(self, url: str, payload: StockAlertNotification) -> bool:
         """POST JSON au webhook. Timeout 10s. Retourne True si 2xx."""
+        if not is_safe_external_url(url):
+            logger.warning("stock_notifier.webhook.blocked_unsafe_url")
+            return False
         timeout = settings.NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS
```

**Point de contrôle — FACT :** le garde est en **première instruction** de `_send_webhook`, avant la construction de `Request` (l.153) et avant `urlopen` (l.163). Aucun chemin ne l'esquive à l'intérieur de cette fonction. `_send_webhook` n'a qu'un seul appelant ([notifier.py:115](app/services/notifier.py:115)). **L'ordonnancement garde-avant-réseau est correct.**

Le garde `is_safe_external_url` **préexiste** au correctif (introduit en `b0c1259`, « durcissement P0–P2 (SSRF…) ») — il n'a pas été modifié ici. Codex a bien « réutilisé » l'existant, sans le durcir.

**Quality gates reproduits en local :**

| Gate | Résultat reproduit |
|------|--------------------|
| `pytest tests/test_stock_notifications.py tests/test_security_hardening.py` | **44 passed** — conforme au rapport |
| `ruff check` (3 fichiers) | **All checks passed** |
| `bandit -r` (notifier + url_safety) | **aucun finding** |

---

## D. Bypass analysis

### D.1 Matrice empirique sur `is_safe_external_url` (exécutée, Python 3.13.13)

| Classe | Échantillon testé | Résultat |
|--------|-------------------|----------|
| Loopback IPv4 | `127.0.0.1`, `127.1`, `127.0.1` | BLOQUÉ |
| Loopback IPv6 | `[::1]`, `[::1]:6379` | BLOQUÉ |
| Link-local / métadonnées | `169.254.169.254` | BLOQUÉ |
| Réseaux privés | `10.0.0.5`, `192.168.1.1`, `172.16.0.1` | BLOQUÉ |
| IPv4-mapped IPv6 | `[::ffff:127.0.0.1]`, `[::ffff:169.254.169.254]`, `[0:0:0:0:0:ffff:a9fe:a9fe]` | BLOQUÉ |
| IPv6 ULA / link-local | `[fc00::1]`, `[fe80::1]` | BLOQUÉ |
| NAT64 / 6to4 | `[64:ff9b::7f00:1]`, `[2002:7f00:1::]` | BLOQUÉ |
| **IPv4 encodé (décimal / hexa / octal)** | `2130706433`, `3232235521`, `2852039166`, `0x7f000001`, `0177.0.0.1` | BLOQUÉ |
| **URL userinfo** | `http://example.com@127.0.0.1/`, `http://user:pass@127.0.0.1/` | BLOQUÉ |
| Alias localhost | `localhost`, `LOCALHOST`, `localhost.`, `LocalHost:8080` | BLOQUÉ |
| Ports arbitraires sur cible interne | `127.0.0.1:22`, `[::1]:6379` | BLOQUÉ |
| Schémas non-HTTP | `file://`, `gopher://`, `ftp://` | BLOQUÉ |
| Casse du schéma | `HTTP://`, `hTTps://` | BLOQUÉ (normalisé par `urlparse`) |
| Unspecified / multicast / broadcast | `0.0.0.0`, `0.0.0.1`, `224.0.0.1`, `255.255.255.255` | BLOQUÉ |
| **CGNAT RFC 6598** | `100.64.0.1` | **AUTORISÉ** |
| **IPv6 site-local (déprécié)** | `[fec0::1]` | **AUTORISÉ** |
| Externe légitime | `8.8.8.8`, `example.com` | autorisé (attendu) |

**Note de robustesse — FACT :** les encodages IPv4 alternatifs sont bloqués **quelle que soit la plateforme**, car le garde valide les **IP résolues** et non seulement les littéraux. Sous glibc/Linux, `getaddrinfo("2130706433")` résout vers `127.0.0.1` → rejeté par `_ip_is_safe`. Sous Windows, la résolution échoue → rejet fail-closed ([url_safety.py:62-63](app/utils/url_safety.py:62)). Les deux branches convergent vers un rejet. **Le design fail-closed sur échec DNS est correct.**

**Résolution multi-IP — FACT :** [url_safety.py:66](app/utils/url_safety.py:66) utilise `all(...)`, donc un nom résolvant vers `[1.2.3.4, 127.0.0.1]` est rejeté. Correct.

### D.2 Redirection HTTP — **BYPASS CONFIRMÉ (PoC exécuté)**

Preuve stdlib inspectée en local :

```
>>> [type(h).__name__ for h in urllib.request.build_opener().handlers]
['UnknownHandler', 'HTTPHandler', 'HTTPDefaultErrorHandler', 'HTTPRedirectHandler',
 'FTPHandler', 'FileHandler', 'DataHandler', 'HTTPSHandler', 'HTTPErrorProcessor']
```

`HTTPRedirectHandler.redirect_request` : `code in (301, 302, 303) and m == "POST"` → suit la redirection en la convertissant en **GET**, jusqu'à `max_redirections = 10`. `http_error_302` n'autorise que `http/https/ftp/''` — **et ne rappelle jamais le garde**.

Sortie PoC (serveurs locaux, aucun fichier du dépôt modifié) :

```
PoC 1 — REDIRECTION HTTP 302 vers un service interne
garde is_safe_external_url('http://attacker.test/webhook') = True
_send_webhook -> True
requetes recues : [('ATTACKER-EDGE', 'POST', '/webhook'),
                   ('INTERNAL-SERVICE', 'GET', '/latest/meta-data/iam/')]
VERDICT PoC1 : BYPASS CONFIRME — le service interne a ete atteint
```

Dans le monde réel l'attaquant n'a **besoin d'aucune ruse DNS** : il héberge son redirecteur sur une IP publique authentique, le garde l'autorise légitimement, puis le redirecteur renvoie `302 Location: http://169.254.169.254/latest/meta-data/`.

**Sous-cas confirmé par lecture stdlib :** `ftp` figure dans l'allowlist de redirection et `FTPHandler` est présent dans l'opener par défaut. Une redirection `302 Location: ftp://10.0.0.5/` **franchit la restriction http/https** portée par le garde.

### D.3 TOCTOU / DNS rebinding — **BYPASS CONFIRMÉ (PoC exécuté)**

```
PoC 2 — TOCTOU / DNS rebinding sur _send_webhook('http://rebind.test/webhook')
  resolution #1 (GARDE)     -> 93.184.216.34 (publique)
  resolution #2 (CONNEXION) -> 127.0.0.1:51286 (interne)
  _send_webhook -> True
  requetes recues : [('INTERNAL-SERVICE', 'POST', '/webhook')]
  VERDICT : BYPASS CONFIRME — POST livre au service interne
```

Le garde résout ([url_safety.py:61](app/utils/url_safety.py:61)) puis **jette le résultat** ; `urlopen` refait sa propre résolution. Avec un TTL DNS de 0 sur un domaine contrôlé, l'attaquant fait pointer la 2ᵉ résolution où il veut. À noter : le **corps JSON complet** (`StockAlertNotification`) est livré à la cible interne, pas seulement une requête GET.

### D.4 Classes vérifiées comme non exploitables

- **Redirection de hostname côté serveur DNS** — couverte par la validation des IP résolues (hors rebinding, §D.3).
- **Confusion de parsing `urlparse` vs `http.client`** — la même chaîne d'URL est passée aux deux ; `http:/\/127.0.0.1/x` donne `hostname=None` → rejeté.
- **Espace de tête, casse, point final FQDN** — normalisés ou rejetés correctement.

---

## E. Test adequacy

### Le test ajouté

```python
def test_blocks_private_network_url(self) -> None:
    notifier = StockNotifier()
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = notifier._send_webhook(
            "http://169.254.169.254/latest/meta-data/", _make_payload()
        )
    assert result is False
    mock_urlopen.assert_not_called()
```

**E.1 — Prouve-t-il réellement l'absence d'appel réseau ? OUI (FACT).**
`patch("urllib.request.urlopen")` remplace bien l'attribut de module effectivement appelé par [notifier.py:163](app/services/notifier.py:163). `assert_not_called()` est l'assertion qui porte la preuve.

**E.2 — Test de mutation exécuté** (garde neutralisé en mémoire, aucun fichier modifié) :

```
[baseline] garde actif      : TEST PASSE
[mutant]   garde neutralise : TEST ECHOUE -> Expected 'urlopen' to not have been called.
                              Called 1 times.  <-- le test DETECTE la regression
```

Le test possède un **réel pouvoir de détection**. À noter : l'assertion `result is False` seule serait **insuffisante** — sans le garde, le `MagicMock` remonte jusqu'à `200 <= status_code < 300`, ce qui lève un `TypeError` capté par le `except Exception` (l.178) et retourne quand même `False`. **C'est `assert_not_called()` qui sauve ce test.** Cette dépendance mérite un commentaire dans le code de test, pour éviter qu'une refonte future ne supprime l'assertion en la croyant redondante.

**E.3 — Couverture : une seule IP.** Le test ne couvre que `169.254.169.254`. La couverture des autres classes repose entièrement sur `tests/test_security_hardening.py` (18 tests), qui teste `is_safe_external_url` **en unitaire** mais **jamais via `_send_webhook`**. Aucun test ne couvre les deux bypass confirmés.

### Tests négatifs manquants

| Manque | Classe |
|--------|--------|
| Redirection 302 vers cible interne | **critique — bypass confirmé** |
| Redirection vers `ftp://` | **critique — bypass confirmé** |
| DNS rebinding / double résolution | **critique — bypass confirmé** |
| `100.64.0.1` (CGNAT RFC 6598) | plage privée non couverte |
| `[fec0::1]` (IPv6 site-local) | plage privée non couverte |
| `http://[::1]/` via `_send_webhook` | loopback IPv6 non testé au niveau service |
| `http://example.com@127.0.0.1/` via `_send_webhook` | userinfo non testé au niveau service |
| Nom d'hôte résolvant vers une IP interne | résolution DNS non testée au niveau service |
| Échec de résolution → fail-closed | comportement de repli non testé |
| `file://`, `gopher://` via `_send_webhook` | schémas non testés au niveau service |
| Nom résolvant vers IP mixtes (publique + interne) | logique `all()` non testée |

---

## F. Related call sites

Recensement exhaustif des primitives réseau sortantes dans `app/` :

| Site | Origine de l'URL | Garde | Statut |
|------|------------------|-------|--------|
| [notifier.py:163](app/services/notifier.py:163) | `NotificationRequest.webhook_url` — **utilisateur** | présent (l.148) | corrigé ici |
| [critical_notifier.py:38](app/services/critical_notifier.py:38) | `NotifConfig.webhook_url` — **utilisateur (officer)** | présent (l.25, + re-check schéma l.28) | préexistant |
| [expiry_notifier.py:90](app/services/expiry_notifier.py:90) | `NotifConfig.webhook_url` — **utilisateur (officer)** | présent (l.81) | préexistant |
| [onmci_client.py:139](app/services/onmci_client.py:139) | `settings.ONMCI_API_URL` — **variable d'environnement** ([config.py:187](app/core/config.py:187)) | absent | **non-SSRF** : entrée non contrôlée par l'utilisateur |

**FACT :** aucun endpoint n'atteint une primitive réseau à partir d'une URL contrôlée par l'utilisateur **sans** passer par le garde. La couverture des call sites est **complète**.

**Conséquence importante :** les bypass §D.2 et §D.3 étant situés **dans le garde et dans `urlopen`**, ils affectent **les trois** call sites, pas seulement celui corrigé. Un correctif porté au niveau de `url_safety.py` ou d'un opener partagé les fermerait tous d'un coup.

---

## G. Findings

---

### P0-SSRF-01 — Contournement du garde par redirection HTTP

- **Severity :** **HIGH**
- **Classification :** **FACT** (PoC exécuté, bypass reproduit)
- **Evidence :**
  - [notifier.py:148](app/services/notifier.py:148) — garde appliqué **une seule fois**, à l'URL initiale.
  - [notifier.py:163](app/services/notifier.py:163) — `urllib.request.urlopen(req, …)` utilise l'**opener par défaut**, qui contient `HTTPRedirectHandler` (vérifié via `build_opener().handlers`).
  - `HTTPRedirectHandler.redirect_request` suit 301/302/303 sur POST (converti en GET), jusqu'à 10 sauts, **sans rappeler `is_safe_external_url`**.
  - PoC : `garde = True` → `[('ATTACKER-EDGE','POST','/webhook'), ('INTERNAL-SERVICE','GET','/latest/meta-data/iam/')]`.
- **Impact :** tout utilisateur authentifié atteint n'importe quel service interne (IMDS cloud, PostgreSQL, Redis, endpoints d'administration, réseau Docker) en hébergeant un redirecteur sur une IP publique légitime. Le garde est intégralement neutralisé. Combiné à P0-SSRF-04, l'attaquant récupère en retour un oracle 2xx.
- **Required remediation :** construire un opener dédié sans suivi de redirection et rejeter explicitement les 3xx :
  ```python
  class _NoRedirect(urllib.request.HTTPRedirectHandler):
      def redirect_request(self, req, fp, code, msg, headers, newurl):
          return None

  _OPENER = urllib.request.build_opener(_NoRedirect)
  # puis : _OPENER.open(req, timeout=timeout)
  ```
  Alternative acceptable : suivre les redirections manuellement en repassant **chaque saut** par `is_safe_external_url`, avec un plafond de sauts. À appliquer aux **trois** call sites (§F).
- **Required regression test :** serveur local renvoyant `302 Location: http://127.0.0.1:<port_interne>/` ; asserter que `_send_webhook` retourne `False` **et** que le serveur interne n'a reçu **aucune** requête (compteur de hits à 0).

---

### P0-SSRF-02 — Échappement du schéma http/https via redirection vers `ftp://`

- **Severity :** **MEDIUM**
- **Classification :** **FACT** (lecture de la stdlib installée ; non exercé par PoC réseau)
- **Evidence :** `HTTPRedirectHandler.http_error_302` autorise `urlparts.scheme in ('http', 'https', 'ftp', '')`, et `FTPHandler` est présent dans l'opener par défaut. Le garde ([url_safety.py:18](app/utils/url_safety.py:18)) ne restreint à http/https que l'URL **initiale**.
- **Impact :** `302 Location: ftp://10.0.0.5/` fait émettre au serveur une connexion FTP interne, hors du modèle de menace couvert par le garde. Portée plus étroite que P0-SSRF-01 (pas de contrôle du corps), mais franchit une restriction explicitement voulue.
- **Required remediation :** résolu automatiquement par le correctif P0-SSRF-01 (désactivation des redirections). Si le suivi manuel est retenu, re-valider le schéma à chaque saut.
- **Required regression test :** asserter qu'une réponse `302 Location: ftp://127.0.0.1/` produit `False` sans qu'aucune connexion FTP ne soit tentée.

---

### P0-SSRF-03 — TOCTOU / DNS rebinding entre validation et connexion

- **Severity :** **MEDIUM-HIGH**
- **Classification :** **FACT** (PoC exécuté, bypass reproduit)
- **Evidence :**
  - [url_safety.py:61](app/utils/url_safety.py:61) — `socket.getaddrinfo(host, None)` : le résultat est **utilisé puis jeté**, jamais réemployé pour la connexion.
  - [notifier.py:163](app/services/notifier.py:163) — `urlopen` déclenche une **seconde** résolution indépendante via `http.client` / `socket.create_connection`.
  - PoC : résolution #1 (garde) → `93.184.216.34` ; résolution #2 (connexion) → `127.0.0.1` ; `_send_webhook -> True` ; `[('INTERNAL-SERVICE','POST','/webhook')]`.
- **Impact :** un domaine attaquant à TTL 0 fait livrer le **POST JSON complet** à un service interne arbitraire. Exploitation moins triviale que P0-SSRF-01 (course à gagner) mais fiable en pratique avec un serveur DNS contrôlé.
- **Required remediation :** épingler l'adresse validée (« pin-and-connect ») : résoudre une fois, valider **toutes** les adresses, puis se connecter à l'IP retenue en conservant l'en-tête `Host` d'origine — via un `HTTPConnection` personnalisé ou un socket pré-résolu. Si cette approche est jugée trop lourde pour le contexte, documenter explicitement l'écart résiduel accepté.
- **Required regression test :** `getaddrinfo` patché renvoyant une IP publique au 1ᵉʳ appel puis `127.0.0.1` au 2ᵉ ; asserter qu'aucune requête n'atteint le serveur local.

---

### P0-SSRF-04 — Oracle de réponse : SSRF aveugle rendue semi-aveugle

- **Severity :** **MEDIUM**
- **Classification :** **FACT**
- **Evidence :**
  - [notifier.py:115-120](app/services/notifier.py:115) — `notifications_sent` vaut 1 **si et seulement si** la cible finale répond 2xx ; sinon `errors` contient un message.
  - [notifier.py:120](app/services/notifier.py:120) — `f"Échec envoi webhook vers {request.webhook_url}"` **réfléchit l'URL fournie** dans la réponse HTTP.
  - PoC 1 : `_send_webhook -> True` après avoir atteint le service interne — le succès est remonté à l'appelant.
  - Canal temporel additionnel : rejet par le garde = immédiat, vs timeout réseau = `NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS`.
- **Impact :** couplé à P0-SSRF-01/03, l'attaquant énumère services et ports internes par différentiel de réponse (cartographie réseau). Pris isolément, l'impact reste faible.
- **Required remediation :** uniformiser le retour côté API — message d'erreur générique sans écho de l'URL, et ne pas distinguer « bloqué » de « échec réseau » dans `errors[]`. Journaliser le détail côté serveur uniquement (le log l.149 est déjà correct sur ce point : il n'inclut pas l'URL).
- **Required regression test :** asserter que la réponse de `POST /stock/notify` pour une URL bloquée ne contient pas la chaîne d'URL soumise, et qu'elle est identique à celle produite par un échec réseau externe.

---

### P0-SSRF-05 — Plage CGNAT RFC 6598 (`100.64.0.0/10`) autorisée

- **Severity :** **MEDIUM**
- **Classification :** **FACT** (matrice empirique)
- **Evidence :**
  - `is_safe_external_url("http://100.64.0.1/x")` → **`True`**.
  - Sondage `ipaddress` : `100.64.0.1` → `is_private=False`, `is_loopback=False`, `is_link_local=False`, `is_reserved=False`, **`is_global=False`**. La liste de prédicats de [url_safety.py:27-34](app/utils/url_safety.py:27) ne teste aucun attribut capturant cette plage.
- **Impact :** `100.64.0.0/10` sert de plage interne sur plusieurs plateformes courantes (AWS/EKS, GKE, VPN maillés type Tailscale). Sur un tel déploiement, la plage interne est joignable **directement**, sans même recourir à P0-SSRF-01/03.
- **Required remediation :** remplacer la liste de prédicats par le prédicat canonique de `ipaddress` :
  ```python
  return ip.is_global and not ip.is_multicast
  ```
  Ce seul changement couvre `100.64.0.0/10`, `192.0.0.0/24`, `198.18.0.0/15` (benchmark) et `fec0::/10` (cf. P0-SSRF-06) — vérifié empiriquement : `is_global` vaut `False` pour tous.
- **Required regression test :** `assert is_safe_external_url("http://100.64.0.1/x") is False`, plus `198.18.0.1` et `192.0.0.1`.

---

### P0-SSRF-06 — IPv6 site-local `fec0::/10` autorisée

- **Severity :** **LOW**
- **Classification :** **FACT** (matrice empirique)
- **Evidence :** `is_safe_external_url("http://[fec0::1]/x")` → **`True`**. Sondage : `fec0::1` → `is_private=False`, `is_reserved=False`, `is_global=True`. Python ne classe pas cette plage dépréciée (RFC 3879) comme privée ; l'attribut dédié `is_site_local` n'est pas consulté par [url_safety.py:27-34](app/utils/url_safety.py:27).
- **Impact :** faible en pratique — plage dépréciée, rarement routée. Constitue néanmoins un trou dans une liste de blocage censée être exhaustive.
- **Required remediation :** couvert par le passage à `is_global` (P0-SSRF-05) ; sinon ajouter `or getattr(ip, "is_site_local", False)`.
- **Required regression test :** `assert is_safe_external_url("http://[fec0::1]/x") is False`.

---

### P0-SSRF-07 — Primitive SSRF accessible au rôle le moins privilégié

- **Severity :** **LOW-MEDIUM**
- **Classification :** **FACT**
- **Evidence :**
  - [stock_notifications.py:40](app/api/v1/endpoints/stock_notifications.py:40) — `_current_user: User = Depends(get_current_active_user)` : **aucun contrôle de rôle**.
  - [api.py:103](app/api/v1/api.py:103) — le routeur est monté **sans** `dependencies=_no_accountant`, contrairement à `critical_alerts_router` ([api.py:79-81](app/api/v1/api.py:79)).
  - Comparaison : le chemin équivalent `POST /critical-alerts/config` exige `require_officer` ([critical_alerts.py:59](app/api/v1/endpoints/critical_alerts.py:59)).
  - Rôles existants : `TECHNICIAN`, `OFFICER`, `ADMIN`, `ACCOUNTANT` ([ruggylab_os.py:27-31](app/models/ruggylab_os.py:27)).
- **Impact :** ce n'est pas une vulnérabilité en soi, mais cela **élargit la population attaquante** de P0-SSRF-01/03 à tout compte actif, y compris `TECHNICIAN` et `ACCOUNTANT` — ce dernier étant par ailleurs explicitement cloisonné hors du domaine clinique. Incohérence de posture entre deux endpoints exposant la même primitive.
- **Required remediation :** aligner sur `/critical-alerts/config` — exiger `require_officer` sur `/stock/notify`, ou justifier explicitement l'écart. Décision métier : à arbitrer par le porteur produit.
- **Required regression test :** un `TECHNICIAN` authentifié appelant `POST /stock/notify` avec `channel=WEBHOOK` reçoit `403`.

---

### P0-SSRF-08 — Absence de contraintes complémentaires sur l'URL sortante

- **Severity :** **LOW**
- **Classification :** **FACT** (absence de code) / **INFERENCE** (sur l'ampleur du risque résiduel)
- **Evidence :**
  - [notification.py:83](app/schemas/notification.py:83) — `webhook_url: str | None`, sans `AnyHttpUrl` ni `max_length` (à comparer avec [notif_config.py:11](app/schemas/notif_config.py:11) qui impose `max_length=500`).
  - [url_safety.py](app/utils/url_safety.py) — aucune restriction de port : `https://<hôte-public>:6379/` est autorisé.
  - Aucune allowlist de destinations, aucun rate-limit sur l'endpoint.
- **Impact :** limité tant que les IP internes sont bloquées. Contribue à la surface : atteinte de services non-HTTP sur hôtes publics, et absence de plafond sur le volume de requêtes sortantes déclenchables.
- **Required remediation :** par ordre de valeur — (1) **allowlist de destinations configurée** (`NOTIFICATION_WEBHOOK_ALLOWED_HOSTS`), qui rendrait les findings 01/03/05/06 largement caducs et constitue le contrôle recommandé pour un contexte ISO 15189 ; (2) à défaut, restreindre les ports à `{80, 443}` et typer le champ en `AnyHttpUrl` avec `max_length`.
- **Required regression test :** `assert is_safe_external_url("https://8.8.8.8:6379/x") is False` ; et, si l'allowlist est retenue, un hôte public hors allowlist rejeté.

---

## Synthèse des priorités

| ID | Severity | Statut | Bloquant push |
|----|----------|--------|---------------|
| P0-SSRF-01 | HIGH | FACT — PoC | **oui** |
| P0-SSRF-03 | MEDIUM-HIGH | FACT — PoC | **oui** |
| P0-SSRF-02 | MEDIUM | FACT | résolu par 01 |
| P0-SSRF-05 | MEDIUM | FACT | recommandé |
| P0-SSRF-04 | MEDIUM | FACT | non |
| P0-SSRF-06 | LOW | FACT | non |
| P0-SSRF-07 | LOW-MEDIUM | FACT | non |
| P0-SSRF-08 | LOW | FACT / INFERENCE | non |

**Ce que le correctif apporte réellement :** il bloque l'exploitation directe (`http://169.254.169.254/`, loopback, RFC 1918, encodages alternatifs, schémas exotiques), il est correctement positionné avant tout accès réseau, il n'introduit **aucune régression**, et il est accompagné d'un test dont le pouvoir de détection a été vérifié par mutation. C'est un progrès net.

**Ce qui manque pour clore le P0 :** deux contournements confirmés par PoC neutralisent le garde en pratique. Le correctif minimal — désactiver le suivi des redirections (P0-SSRF-01/02) — représente environ 5 lignes et ferme le vecteur le plus exploitable, sur les trois call sites à la fois.

---

P0_SSRF_RECOMMENDATION:
NEEDS_FIX_BEFORE_PUSH
