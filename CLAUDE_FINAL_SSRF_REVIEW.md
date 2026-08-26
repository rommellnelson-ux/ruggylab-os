# CLAUDE_FINAL_SSRF_REVIEW

Revue adversariale finale — remédiation SSRF n°2
Réviseur : Principal Application Security Reviewer (indépendant)
Date : 2026-08-24 · Branche : `feat/acquisition-3-flux` · Python 3.13.13 · pytest 9.0.3
Aucun fichier source modifié · aucun commit · aucun push.

Convention : **FACT** = démontré par exécution ou lecture directe du code ·
**INFERENCE** = déduit, non exécutable ici · **UNKNOWN** = non déterminable.

---

## 1. Verdict exécutif

Les **deux P0 de la revue précédente sont réellement fermés**, et je le démontre
sur le fil (socket réel), pas sur des compteurs de tests :

| P0 précédent | Statut | Preuve |
|---|---|---|
| P0-SSRF-01/02 — bypass par redirection HTTP | **FERMÉ (FACT)** | 11 classes de redirection testées sur un vrai serveur : **1 seul hit serveur** dans tous les cas |
| P0-SSRF-03 — TOCTOU / DNS rebinding | **FERMÉ (FACT)** | `getaddrinfo` piégé pour lever une exception après validation → la connexion aboutit quand même sur l'IP épinglée |

**Aucun P0 ne survit.** Mais quatre P1 subsistent, dont **deux revendications
Codex sont factuellement fausses** :

- « Host header protected » → **FALSIFIÉ** (F-01, reproduit sur le fil).
- « centralized outbound HTTP transport » → **FALSIFIÉ** (F-04 : `onmci_client.py`
  reste sur `urllib.request.urlopen`, suit les redirections, sans épinglage).

S'y ajoutent une politique d'adresses incomplète (F-02 : NAT64, IPv4-compatible,
multicast acceptés) et un test TLS tautologique qui ne protège rien (F-03).

**Verdict : PARTIEL — corriger F-01, F-02, F-03 avant push ; trancher F-04.**
Les correctifs F-01/F-02/F-03 représentent ~15 lignes et 3 tests.

---

## 2. Architecture revue

```
POST /api/v1/stock-notifications      (get_current_active_user — rôle le plus bas)
POST /api/v1/critical-alerts/config   (require_officer)          NotifConfig.webhook_url
POST /api/v1/critical-alerts/expiry-check
        │
        ├── app/services/notifier.py           StockNotifier._send_webhook
        ├── app/services/critical_notifier.py  _send_webhook
        └── app/services/expiry_notifier.py    check_and_notify_expiry
                        │
                        ▼
             app/utils/safe_http.safe_post_json          ← transport central (NOUVEAU)
                 resolve_public_target()  : parse → 1 seul getaddrinfo → valide TOUTES
                                            les réponses → épingle validated[0]
                 _PinnedHTTPConnection    : connect() intégralement surchargé,
                                            socket.connect(sockaddr épinglé)
                 _PinnedHTTPSConnection   : wrap_socket(server_hostname=hostname d'origine)
                 pas de suivi de redirection · Host imposé par le transport
```

Le webhook est **contrôlable par l'utilisateur** : `NotificationRequest.webhook_url`
est un `str | None` libre ([app/schemas/notification.py:83](app/schemas/notification.py:83)),
consommé par un endpoint qui n'exige que `get_current_active_user`
([app/api/v1/endpoints/stock_notifications.py:37](app/api/v1/endpoints/stock_notifications.py:37)).
La primitive SSRF reste donc accessible au rôle le moins privilégié — c'est le
contexte qui fixe la sévérité de tout ce qui suit.

---

## 3. Évaluation de l'invariant de sécurité

> « La destination réseau finalement contactée est la même destination publique
> validée qui a passé la validation SSRF. »

L'invariant se décompose en cinq sous-propriétés. Quatre sont démontrées, la
cinquième est **partiellement fausse**.

| # | Sous-propriété | Statut | Preuve |
|---|---|---|---|
| 3.1 | Résolution DNS effectuée **une seule fois** | **VRAI (FACT)** | `resolver.assert_called_once_with(...)` + harnais indépendant : `getaddrinfo` compté à 1 sur 6 scénarios de bout en bout |
| 3.2 | La connexion vise le `sockaddr` épinglé | **VRAI (FACT)** | `sock.getpeername()` == `('127.0.0.1', 55023)` == `target.sockaddr` |
| 3.3 | Aucune 2ᵉ résolution entre validation et connexion | **VRAI (FACT)** | `getaddrinfo` remplacé par `side_effect=AssertionError` après `resolve_public_target` → la requête aboutit (status 204) : le chemin de connexion ne touche jamais le résolveur |
| 3.4 | Aucune redirection suivie | **VRAI (FACT)** | §6 — 11 classes, 1 hit serveur chacune |
| 3.5 | La destination validée est **publique** | **PARTIELLEMENT FAUX (FACT)** | §9 — NAT64 `64:ff9b::/96`, IPv4-compatible `::/96`, multicast et `192.88.99.0/24` passent le prédicat |

**Conclusion.** Le mécanisme d'épinglage est correct et démontré : ce qui est
validé est bien ce qui est composé. C'est la **définition de « publique »** qui
est incomplète. L'invariant tient au sens mécanique, mais le prédicat qu'il
protège laisse passer des classes d'adresses qui encapsulent du loopback et le
service de métadonnées.

Preuve directe que ces adresses atteignent l'étage de composition :

```
64:ff9b::a9fe:a9fe     -> PINNED AND WILL BE DIALED: ('64:ff9b::a9fe:a9fe', 80, 0, 0)
::7f00:1               -> PINNED AND WILL BE DIALED: ('::7f00:1', 80, 0, 0)
224.0.0.1              -> PINNED AND WILL BE DIALED: ('224.0.0.1', 80)
```

`64:ff9b::a9fe:a9fe` est l'encodage NAT64 de **169.254.169.254**.

---

## 4. Matrice d'attaque (exécutée)

### A/B — Destinations directes et encodages d'adresse

`getaddrinfo` instrumenté pour renvoyer le littéral ; `resolve_public_target` réel.

| Adresse | Résultat | Adresse | Résultat |
|---|---|---|---|
| `127.0.0.1` | rejetée | `::1` | rejetée |
| `0.0.0.0` | rejetée | `fe80::1` | rejetée |
| `10.0.0.5` / `172.16.9.9` / `192.168.1.1` | rejetées | `fc00::1` | rejetée |
| `169.254.169.254` | rejetée | `2001:db8::1` | rejetée |
| `100.64.0.1` (CGNAT) | rejetée | `::ffff:127.0.0.1` | rejetée |
| `255.255.255.255` | rejetée | `::ffff:10.0.0.1` | rejetée |
| `198.18.0.1` | rejetée | `8.8.8.8` | acceptée (attendu) |
| **`224.0.0.1`** | **ACCEPTÉE** | **`ff02::1`** | **ACCEPTÉE** |
| **`239.255.255.250`** | **ACCEPTÉE** | **`::7f00:1`** | **ACCEPTÉE** |
| **`192.88.99.1`** | **ACCEPTÉE** | **`64:ff9b::7f00:1`** | **ACCEPTÉE** |
| | | **`64:ff9b::a9fe:a9fe`** | **ACCEPTÉE** |

Encodages IPv4 alternatifs (`2130706433`, `0x7f000001`, `0177.0.0.1`, `127.1`) :
tous rejetés — non pas par une liste noire de chaînes, mais parce que la
validation porte sur le `sockaddr` **résolu**, ce qui est la bonne conception.
(Sur cette plateforme ils échouent en amont à la résolution ; sur une glibc qui
les résoudrait, la validation post-résolution les capterait tout de même.
Classification : **FACT** ici, **INFERENCE** pour glibc.)

### C — Analyse d'URL et de nom d'hôte

| Entrée | Résultat |
|---|---|
| `http://localhost/h`, `localhost./h`, `LOCALHOST/h`, `LocalHost./h` | rejetées (adresse non publique) — casse et point final normalisés |
| `http://user@example.com/h` | rejetée (userinfo interdit) |
| `http://user:pass@example.com/h` | rejetée (userinfo interdit) |
| `http://%75ser@example.com/h` | rejetée (userinfo interdit) |
| `http:///h`, `http://:80/h` | rejetées (hostname requis) |
| `http://example.com:99999/h`, `:notaport` | rejetées (URL malformée) |
| `file://`, `gopher://`, `ftp://`, `//example.com/h`, `""` | rejetées (schéma) |
| `http://[fe80::1%25eth0]/h` | rejetée (zone identifier) |
| `http://example.com#@127.0.0.1/` | acceptée → résout `example.com` (**correct**) |
| `http://example.com\r\nX-Evil: 1/h` | rejetée (URL malformée) |
| `http://example.com:0/h` | acceptée → port 0 retombe silencieusement sur 80 (F-10, sans impact) |

### D — Jeux de réponses DNS

| Scénario | Résultat |
|---|---|
| publique seule | acceptée, épinglée |
| privée seule | rejetée |
| **publique puis privée** | **rejetée** |
| **privée puis publique** | **rejetée** |
| deux publiques / doublons | acceptée (première épinglée) |
| v4 publique + v6 publique | acceptée |
| v4 publique + v6 privée | **rejetée** |
| v6 publique + v4 privée | **rejetée** |
| réponse vide | rejetée |
| famille non AF_INET/AF_INET6 | rejetée |
| `SOCK_DGRAM` glissé dans la réponse | rejetée |
| échec du résolveur (`gaierror`) | **rejetée — fail-closed** |

La validation est bien **conjonctive** (toutes les réponses, pas seulement
celle utilisée) : c'est la bonne propriété, et elle neutralise le réordonnancement.

---

## 5. Analyse DNS rebinding

**Il ne peut pas y avoir de seconde résolution entre validation et connexion — FACT.**

Preuve par code : `_PinnedHTTPConnection.connect()`
([app/utils/safe_http.py:116](app/utils/safe_http.py:116)) surcharge intégralement
la méthode parente et n'appelle jamais `self._create_connection` ni
`socket.create_connection`. Elle construit le socket depuis `target.family /
socktype / proto` et appelle `sock.connect(target.sockaddr)`. `self.host` /
`self.port` hérités ne servent qu'à l'identité de l'objet ; l'en-tête `Host`
est fourni explicitement, donc `putrequest` ne les relit pas non plus.

Preuve par exécution (harnais indépendant du test livré) :

```
7. DNS rebinding (public at validation, private at connect time):
   pinned sockaddr=('127.0.0.1', 55023)  getaddrinfo calls during resolve=1
   connected+responded status=204 peer_of_sock=('127.0.0.1', 55023)
```

`getaddrinfo` était remplacé par `side_effect=AssertionError("SECOND DNS
RESOLUTION OCCURRED")` pendant toute la phase de connexion. Elle n'a jamais été
levée.

Fenêtre TOCTOU résiduelle : nulle au niveau applicatif. Le seul rebinding
restant serait au niveau du **routage/NAT en aval**, hors périmètre applicatif —
et c'est précisément par là que F-02 (NAT64) devient exploitable.

---

## 6. Analyse des redirections

Politique implémentée : **aucune redirection n'est suivie**, jamais.
`safe_post_json` lit `response.status`, ferme, et rend le code — le champ
`Location` n'est jamais lu ([app/utils/safe_http.py:166](app/utils/safe_http.py:166)).

Vérification sur socket réel (serveur de test comptant les hits) :

```
case                    status  server_hits  paths
301 -> metadata            301       1
302 -> metadata            302       1
303 -> loopback            303       1
307 -> RFC1918             307       1
308 -> RFC1918             308       1
302 relative               302       1       ['/r302?loc=/internal/admin']
302 -> ftp scheme          302       1
302 -> file scheme         302       1
302 -> other public        302       1
302 chain step1            302       1
200 control                204       1
```

Toutes les classes exigées par la matrice — 301/302/303/307/308, relatif,
absolu, chaîne, public→privé, public→métadonnées, public→autre public,
changement de schéma — donnent **exactement un hit serveur**. Le P0-SSRF-01 et
le P0-SSRF-02 (évasion de schéma via `Location: ftp://`) sont fermés.

Effet de bord côté appelant : les trois notifiers traitent un 3xx comme un échec
(`200 <= status < 300`), ce qui est le comportement souhaitable.

---

## 7. Analyse TLS / SNI / certificat

Posture **de production** relevée en instanciant réellement `_connection_for`
sur une cible `https` sans contexte injecté :

```
class=_PinnedHTTPSConnection check_hostname=True verify_mode=2 (CERT_REQUIRED)
min_version=771 (TLSv1.2) cafile_loaded=True
```

- TCP vise l'IP validée : **oui** — `_PinnedHTTPSConnection.connect()` appelle
  `_connect_validated_socket()` avant tout TLS ([safe_http.py:131](app/utils/safe_http.py:131)).
- SNI = nom d'hôte d'origine : **oui** — `wrap_socket(server_hostname=self._target.hostname)`.
- Vérification de certificat active : **oui** — `ssl.create_default_context()`, non altéré.
- Nom d'hôte vérifié contre l'hôte d'origine : **oui** (`check_hostname=True` + SNI d'origine).
- Équivalent `verify=False` : **aucun** dans le module.
- Repli silencieux désactivant la validation : **aucun** — l'échec de `wrap_socket`
  ferme le socket brut et propage l'exception ([safe_http.py:137](app/utils/safe_http.py:137)).

**Mais** : aucun test ne protège cette posture (voir F-03). La revendication TLS
est vraie aujourd'hui et non régressée-testée.

---

## 8. Analyse de l'en-tête Host

L'en-tête est imposé par le transport via l'ordre du dictionnaire :
`{**(headers or {}), "Content-Type": ..., "Host": target.host_header}`
([safe_http.py:159](app/utils/safe_http.py:159)).

Sur le fil, avec un vrai serveur enregistrant `get_all("Host")` :

| Cas | En-tête(s) Host réellement émis |
|---|---|
| aucun header appelant | `['hooks.example:55023']` |
| appelant `{"Host": "attacker.invalid"}` | `['hooks.example:55023']` — neutralisé ✔ |
| appelant **`{"host": "attacker.invalid"}`** | **`['attacker.invalid', 'hooks.example:55023']`** ✘ |
| appelant `{"Content-Type": "text/plain"}` | Content-Type du transport conservé ✔ |
| appelant `{"X-A": "b\r\nHost: evil"}` | `ValueError: Invalid header value` — injection CRLF bloquée par `http.client` ✔ |

La fusion étant **sensible à la casse** alors que les en-têtes HTTP ne le sont
pas, une clé `host` en minuscules survit et sort **avant** le Host du transport.
De nombreux serveurs et proxies retiennent le **premier** Host. Voir F-01.

`http.client` protège par ailleurs contre l'injection CRLF dans les noms et
valeurs d'en-tête, et contre les caractères interdits dans la request-target.

---

## 9. Analyse de la politique d'adresses IP

`_is_public_address` ([safe_http.py:34](app/utils/safe_http.py:34)) délègue
entièrement à `ipaddress.is_global`, avec un traitement spécial correct pour
`::ffff:0:0/96` (IPv4-mapped, vérifié des deux côtés).

Ce que `is_global` renvoie **True** sur Python 3.13.13 (mesuré) :

| Plage | Exemple | `is_global` | Conséquence |
|---|---|---|---|
| NAT64 well-known | `64:ff9b::a9fe:a9fe` | **True** | = 169.254.169.254 derrière une passerelle NAT64 |
| NAT64 well-known | `64:ff9b::7f00:1` | **True** | = 127.0.0.1 derrière NAT64 |
| IPv4-compatible (déprécié) | `::7f00:1` | **True** | encapsule 127.0.0.1 |
| Multicast IPv4 | `224.0.0.1`, `239.255.255.250` | **True** | non routable en TCP (impact faible) |
| Multicast IPv6 | `ff02::1` | **True** | idem |
| Relais 6to4 anycast | `192.88.99.1` | **True** | déprécié RFC 7526 |

Ce que `is_global` rejette correctement : loopback, RFC1918, link-local
(169.254.0.0/16 incluse), **CGNAT 100.64.0.0/10**, benchmark 198.18.0.0/15,
TEST-NET, `0.0.0.0/8`, broadcast, ULA `fc00::/7`, `fe80::/10`, `2001:db8::/32`,
Teredo `2001::/32`, `100::/64`, **6to4 `2002::/16`**, IPv4-mapped privées.

Les revendications « CGNAT rejeté », « IPv6 loopback rejeté », « IPv4-mapped
privées rejetées », « résultats DNS mixtes rejetés » sont **vraies (FACT)**.
La couverture est bonne ; ce sont les formes d'**encapsulation IPv4 dans IPv6**
autres que `::ffff:` qui manquent. Voir F-02.

---

## 10. Inventaire des sorties réseau (`app/`)

Recherche exhaustive : `urllib.request|urlopen|requests\.|httpx|aiohttp|http.client|socket.create_connection|socket.socket|getaddrinfo|smtplib|ftplib|paramiko|pycurl|urllib3`.

| # | Emplacement | Primitive | Classification | Remarque |
|---|---|---|---|---|
| 1 | [app/utils/safe_http.py:148](app/utils/safe_http.py:148) `safe_post_json` | `http.client` épinglé | **SAFE CENTRAL TRANSPORT** + **USER-CONTROLLABLE DESTINATION** | seule primitive à destination utilisateur |
| 2 | [app/services/notifier.py:149](app/services/notifier.py:149) | → #1 | SAFE CENTRAL TRANSPORT | ✔ centralisé |
| 3 | [app/services/critical_notifier.py:24](app/services/critical_notifier.py:24) | → #1 | SAFE CENTRAL TRANSPORT | ✔ centralisé |
| 4 | [app/services/expiry_notifier.py:85](app/services/expiry_notifier.py:85) | → #1 | SAFE CENTRAL TRANSPORT | ✔ centralisé |
| 5 | [app/services/onmci_client.py:138](app/services/onmci_client.py:138) | `urllib.request.urlopen` | **CONFIGURATION-ONLY DESTINATION** — *non centralisé* | **suit les redirections**, pas d'épinglage → F-04 |
| 6 | [app/services/notifier.py:211](app/services/notifier.py:211) | `smtplib.SMTP` | CONFIGURATION-ONLY | `SMTP_HOST`/`SMTP_PORT` |
| 7 | [app/services/report_delivery_outbox.py:160](app/services/report_delivery_outbox.py:160) | `smtplib.SMTP` | CONFIGURATION-ONLY | idem |
| 8 | [app/utils/url_safety.py:61](app/utils/url_safety.py:61) | `socket.getaddrinfo` | **CODE MORT en production** | plus aucun appelant applicatif → F-06 |
| 9 | listeners DH36 / raw TCP, Redis, PostgreSQL | — | entrant / configuration | hors périmètre SSRF |

`app/api/v1/endpoints/notifications.py` ne contient que du WebSocket **entrant**
(Starlette), pas de sortie.

**Aucun chemin alternatif contrôlable par l'utilisateur ne contourne le nouveau
transport (FACT).** Le seul contournement est #5, dont la destination est
gouvernée par une variable d'environnement.

---

## 11. Qualité des tests de régression

Suites exécutées ici : `tests/test_safe_http.py` (11) + `tests/test_stock_notifications.py`
(26) + `tests/test_security_hardening.py` (18) = **55 passed**. Je n'ai pas
cherché à reproduire la sélection de fichiers derrière le chiffre « 96 passed »
annoncé ; les compteurs ne sont pas une preuve et ne sont pas traités comme telle.
`ruff check` : PASS. `ruff format --check` : 73 fichiers déjà formatés.
`bandit -r app/utils/safe_http.py app/services/` : **No issues identified**.

Mutation testing conduit **en mémoire** (`unittest.mock` sur les attributs de
module), aucun fichier disque touché ; baseline re-vérifiée verte après chaque
restauration.

| Mutant réintroduit | Test censé l'attraper | Résultat |
|---|---|---|
| M1 — suivi de redirection (récursif) | `test_redirect_response_is_returned_and_never_followed` | **tué** |
| M1b — suivi d'**une seule** redirection | idem | **tué** (`response.getheader.assert_not_called()`) |
| M2 — suppression de l'épinglage (re-résolution au connect) | `test_connection_uses_validated_ip_without_second_dns_resolution` | **tué** (`Expected 'getaddrinfo' to be called once. Called 2 times.`) |
| M4 — inversion d'ordre : headers appelant > Host transport | `test_redirect_response_is_returned_and_never_followed` | **tué** |
| **M3 — `check_hostname=False; verify_mode=CERT_NONE` dans le défaut de production** | `test_https_connects_to_pinned_ip_and_preserves_tls_hostname` | **SURVIT** ✘ |

Les revendications « le test de redirection échoue si la protection est retirée »
et « le test de rebinding échoue si l'épinglage est retiré » sont donc
**vérifiées et vraies (FACT)**. Le mutant vulnérable a été restauré et la
baseline repasse au vert (FACT).

En revanche `test_https_connects_to_pinned_ip_and_preserves_tls_hostname`
([tests/test_safe_http.py:102](tests/test_safe_http.py:102)) injecte son
propre `MagicMock(spec=ssl.SSLContext)` sur lequel **le test lui-même** pose
`check_hostname = True` (l.117) et `verify_mode = CERT_REQUIRED` (l.118), puis
les ré-assertionne aux lignes 127-128. C'est une tautologie : elle ne peut pas
échouer. Voir F-03.

Trous de couverture négative restants : aucun test ne couvre NAT64 / IPv4-compatible /
multicast, ni la variante `host` en minuscules, ni la posture TLS par défaut,
ni le fail-closed sur `gaierror` (comportement pourtant correct, vérifié ici
manuellement).

---

## 12. Constats restants

### F-01 — Contrebande d'en-tête `Host` par variante de casse

- **Sévérité** : P1
- **Classification** : **FACT** (reproduit sur socket réel)
- **Prérequis d'attaque** : un appelant de `safe_post_json` doit passer une clé
  d'en-tête contrôlée par l'attaquant. Aucun site d'appel actuel ne le fait
  (les trois notifiers ne passent qu'un `User-Agent` littéral) → **latent**.
- **Preuve** :
  ```
  headers actually sent = {'host': 'attacker.invalid',
                           'Content-Type': 'application/json',
                           'Host': 'public.example'}
  ── sur le fil ──
  Host header(s) = ['attacker.invalid', 'hooks.example:55023']
  ```
  `safe_http.py:159-163` fusionne en respectant la casse ; HTTP ne la respecte pas.
- **Impact** : routage virtual-host vers une cible non voulue sur l'IP validée ;
  amorce de désynchronisation de requêtes devant un proxy qui retient le premier `Host`.
- **Exploitabilité** : nulle aujourd'hui, immédiate dès qu'un futur appelant
  propage des en-têtes issus de la configuration ou de la requête. La revendication
  « caller-provided headers cannot defeat the transport-selected Host » est fausse.
- **Remédiation exigée** : filtrer les en-têtes appelants de façon
  **insensible à la casse** avant fusion, et refuser (ou écraser) les en-têtes
  réservés `host`, `content-length`, `transfer-encoding`, `connection`, `expect`.
- **Test de régression exigé** : `{"host": ...}`, `{"HOST": ...}`, `{"HoSt": ...}`,
  `{"content-length": "0"}` → assertion qu'un **seul** `Host` atteint le fil et
  qu'il vaut `target.host_header`.

### F-02 — Encapsulations IPv4-dans-IPv6 et multicast admis comme « publics »

- **Sévérité** : P1
- **Classification** : **FACT** pour l'acceptation ; **INFERENCE** pour
  l'exploitabilité en production (dépend de la présence d'une passerelle NAT64/DNS64).
- **Prérequis d'attaque** : utilisateur authentifié (rôle le plus bas) capable de
  publier un enregistrement AAAA pour un nom qu'il contrôle, **et** un chemin
  réseau NAT64/DNS64. Le déploiement docker-compose actuel n'en montre pas
  (INFERENCE : IPv6 non configuré dans `docker-compose.yml`) — d'où P1 et non P0.
- **Preuve** :
  ```
  64:ff9b::a9fe:a9fe  -> PINNED AND WILL BE DIALED   (= 169.254.169.254)
  64:ff9b::7f00:1     -> PINNED AND WILL BE DIALED   (= 127.0.0.1)
  ::7f00:1            -> PINNED AND WILL BE DIALED   (IPv4-compatible, RFC 4291 déprécié)
  224.0.0.1 / 239.255.255.250 / ff02::1 -> ACCEPTÉES (multicast)
  192.88.99.1         -> ACCEPTÉE                    (relais 6to4 anycast)
  ```
- **Impact** : SSRF vers le service de métadonnées et le loopback dans tout
  déploiement IPv6-only/NAT64 (cloud managé, Kubernetes IPv6-only). Multicast :
  impact quasi nul en TCP, mais l'acceptation est une faiblesse de politique.
- **Exploitabilité** : conditionnelle mais triviale une fois la condition remplie ;
  aucune modification de code applicatif n'est nécessaire côté attaquant.
- **Remédiation exigée** : dans `_is_public_address`, après `is_global`, rejeter
  explicitement `is_multicast`, `is_reserved`, `is_unspecified` ; et pour IPv6,
  extraire toute IPv4 encapsulée — `::ffff:0:0/96` (déjà fait), `::/96`
  IPv4-compatible, `64:ff9b::/96` et `64:ff9b:1::/48` (NAT64), `2002::/16`
  (6to4) — puis revalider l'IPv4 extraite ; rejeter enfin `192.88.99.0/24`.
- **Test de régression exigé** : paramétrer les six littéraux ci-dessus et
  assertionner `UnsafeOutboundUrlError` **sans qu'aucun socket ne soit créé**
  (même forme que `test_non_public_destinations_are_rejected_without_socket`).

### F-03 — Le test TLS est tautologique : une régression `verify=False` passerait

- **Sévérité** : P1 (qualité de test ; le code de production est correct aujourd'hui)
- **Classification** : **FACT** (mutation exécutée)
- **Prérequis** : aucun — c'est un défaut de filet de sécurité, pas une vulnérabilité active.
- **Preuve** : mutant M3 posant `check_hostname=False; verify_mode=CERT_NONE`
  dans la branche par défaut de `_PinnedHTTPSConnection.__init__` →
  `test_https_connects_to_pinned_ip_and_preserves_tls_hostname` **reste vert**.
  Cause : le test fournit `context=` et assertionne des attributs qu'il a lui-même
  positionnés ([tests/test_safe_http.py:116](tests/test_safe_http.py:116) vs l.127-128).
- **Impact** : un futur « fix » désactivant la vérification de certificat (motif
  classique : « le webhook du partenaire a un certificat auto-signé ») serait
  mergé sans qu'aucun test ne rougisse. MITM sur tous les webhooks HTTPS.
- **Exploitabilité** : nulle en l'état ; risque de régression future élevé.
- **Remédiation exigée** : ajouter un test qui construit la connexion **sans**
  injecter de contexte (`_connection_for(https_target, timeout)`) et assertionne
  `ctx.check_hostname is True`, `ctx.verify_mode is ssl.CERT_REQUIRED`,
  `ctx.minimum_version >= ssl.TLSVersion.TLSv1_2`, `ctx.get_ca_certs() != []`.
- **Test de régression exigé** : celui ci-dessus (il tue M3 par construction).

### F-04 — Deuxième sortie HTTP non centralisée, qui suit les redirections

- **Sévérité** : P1
- **Classification** : **FACT** (lecture de code)
- **Prérequis d'attaque** : `ONMCI_API_URL` configurée (défaut `None`), **et**
  contrôle de l'endpoint ONMCI (compromission, détournement DNS, MITM sur `http://`).
- **Preuve** : [app/services/onmci_client.py:138](app/services/onmci_client.py:138)
  ```python
  req = urllib.request.Request(url, method="GET")
  with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
  ```
  `urlopen` suit 301/302/303/307/308 par défaut, re-résout le DNS et n'épingle
  aucune IP — exactement les deux P0 fermés ailleurs.
- **Impact** : SSRF de second ordre vers le réseau interne / métadonnées, avec
  lecture du corps de réponse (`resp.read()`) — donc **non aveugle**.
- **Exploitabilité** : indirecte (destination gouvernée par la configuration).
  Falsifie la revendication « centralized outbound HTTP transport » et constitue
  le candidat le plus probable pour l'alerte CodeQL SSRF encore ouverte
  (**INFERENCE** : je n'ai pas accès au rapport CodeQL ; aucun workflow CodeQL
  n'existe dans `.github/workflows/`).
- **Remédiation exigée** : ajouter `safe_get_json` au transport central et y
  router `_verify_remote`, ou documenter explicitement l'exclusion de périmètre.
- **Test de régression exigé** : `assert onmci_client.safe_get_json is safe_http.safe_get_json`
  + un test prouvant qu'une redirection retournée par l'API ONMCI n'est pas suivie.

### F-05 — Le jeton de vérification ONMCI est journalisé dans l'URL

- **Sévérité** : P2 · **Classification** : **FACT**
- **Preuve** : [app/services/onmci_client.py:158](app/services/onmci_client.py:158) —
  `extra={"url": url}` où `url = f"{api_url}/verify?token=...&prescriber=..."`.
- **Impact** : fuite de secret de vérification dans les journaux applicatifs
  (rétention, export, sauvegardes). Sensible ISO 15189 / protection des données.
- **Remédiation exigée** : journaliser l'URL sans la query string.
- **Test exigé** : `caplog` — assertion que le jeton n'apparaît dans aucun enregistrement.

### F-06 — Validateur hérité `url_safety.py` conservé, sans appelant applicatif

- **Sévérité** : P2 · **Classification** : **FACT**
- **Preuve** : plus aucun import sous `app/` (seuls `tests/test_security_hardening.py`
  et des worktrees `.claude/` s'y réfèrent). C'est le validateur **vulnérable au
  TOCTOU** de la revue précédente : il valide une URL puis rend la main à un
  appelant qui re-résout.
- **Impact** : un futur développeur le réutilisera de bonne foi et réintroduira
  P0-SSRF-03. Ses 18 tests verts lui donnent une apparence de contrôle maintenu.
- **Remédiation exigée** : supprimer le module et ses tests, ou ajouter un
  `DeprecationWarning` explicite au niveau du module renvoyant vers `safe_http`.

### F-07 — Pas de politique de port ni de liste d'autorisation ; oracle 1 bit persistant

- **Sévérité** : P2 · **Classification** : **FACT**
- **Preuve** : `resolve_public_target` accepte tout port ; `safe_post_json` rend
  le code HTTP, que `notify()` traduit en succès/échec dans `NotificationResult.errors`.
- **Impact** : un utilisateur authentifié de rang le plus bas peut faire émettre
  par le serveur des POST arbitraires vers n'importe quel hôte **public**, port
  compris, et lire 1 bit de réponse — balayage de ports Internet et relais d'abus
  depuis l'IP de l'établissement. Le P0-SSRF-04/07 précédent est fortement réduit
  (le périmètre interne est fermé) mais pas éliminé.
- **Remédiation recommandée** : liste blanche d'hôtes de webhook en configuration,
  ou à défaut restriction aux ports 80/443 + limitation de débit par utilisateur.

### F-08 — Pas d'échéance globale : seulement un timeout par opération

- **Sévérité** : P2 · **Classification** : **INFERENCE** (analyse de code, non exécutée)
- **Preuve** : `sock.settimeout(self.timeout)` ([safe_http.py:109](app/utils/safe_http.py:109))
  s'applique à chaque opération, pas à la requête entière.
- **Impact** : un serveur qui envoie ses en-têtes octet par octet peut retenir un
  worker du threadpool FastAPI jusqu'à ~`_MAXHEADERS (100) × timeout`. Avec
  `NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS = 10`, plusieurs minutes par requête.
  Disponibilité uniquement.
- **Remédiation recommandée** : échéance monotone globale vérifiée avant `getresponse()`.

### F-09 — Changement de comportement : plus de support de proxy sortant

- **Sévérité** : P2 · **Classification** : **FACT** (code) / **INFERENCE** (impact nul ici)
- **Preuve** : `http.client` ignore `HTTP_PROXY`/`HTTPS_PROXY` ; `urllib.request`
  les honorait. Aucun proxy sortant n'est configuré (`.env.example`,
  `docker-compose.yml` : seul un reverse-proxy Caddy **entrant**).
- **Impact** : nul aujourd'hui ; les webhooks casseraient silencieusement si
  l'établissement imposait plus tard un proxy d'égress.
- **Remédiation recommandée** : documenter la contrainte dans `.env.example`.

### F-10 — Taxonomie d'erreurs et port 0

- **Sévérité** : P2 · **Classification** : **FACT**
- Corps > 1 MiB lève un `ValueError` nu et non `UnsafeOutboundUrlError`
  ([safe_http.py:157](app/utils/safe_http.py:157)) — incohérent, sans impact
  (les appelants attrapent `Exception`).
- `http://example.com:0/h` : `port or _DEFAULT_PORTS[scheme]` fait retomber le
  port 0 sur 80 silencieusement. Direction sûre, mais surprenante.

---

## 13. Risque résiduel

**Fermé et démontré**
Bypass par redirection (toutes classes) · DNS rebinding / TOCTOU · loopback,
RFC1918, link-local, métadonnées cloud, CGNAT, IPv6 ULA/link-local/loopback,
IPv4-mapped privées, jeux DNS mixtes, userinfo, schémas non-HTTP, injection CRLF,
fail-closed sur échec de résolution, TLS vérifié vers l'IP épinglée avec le SNI d'origine.

**Ouvert**

| Risque | Probabilité | Impact | Net |
|---|---|---|---|
| F-02 SSRF via NAT64 vers métadonnées | faible (dépend de NAT64) | élevé | **P1** |
| F-04 SSRF de second ordre via ONMCI | faible (config + hôte hostile) | élevé | **P1** |
| F-01 contrebande de Host | très faible aujourd'hui, latente | moyen | **P1** |
| F-03 régression TLS non détectée | moyenne (dette de test) | élevé si réalisée | **P1** |
| F-07 relais d'abus / scan de ports publics | moyenne | faible-moyen | P2 |
| F-05 fuite de jeton en journal | certaine si ONMCI activé | moyen | P2 |
| F-06 réutilisation du validateur hérité | moyenne | élevé si réalisée | P2 |

Hors périmètre confirmé : les constats Pillow de `pip-audit`, et l'alerte CodeQL
SSRF (non revendiquée close — cohérent avec F-04, qui en est le candidat le plus
plausible sans que je puisse le confirmer).

---

## 14. Recommandation

La remédiation n°2 est un progrès réel et vérifiable : la conception —
résolution unique, validation conjonctive de **toutes** les réponses, épinglage
du `sockaddr` validé, `connect()` intégralement surchargé, aucune redirection,
TLS d'origine préservé — est la bonne, et je l'ai confirmée sur socket réel et
par mutation, pas sur des compteurs de tests. **Les deux P0 sont fermés.**

Je ne peux pas pour autant conclure à SAFE_TO_PUSH : deux revendications
explicites de Codex sont **factuellement falsifiées** (« Host header protected »,
« centralized outbound HTTP transport »), le prédicat « publique » laisse passer
des adresses qui encapsulent le loopback et le service de métadonnées, et le
seul test TLS est une tautologie qui laisserait passer un `verify=False`.

**Bloquant avant push** — F-01, F-02, F-03 (~15 lignes de code, 3 tests) :

1. Fusion d'en-têtes insensible à la casse + refus des en-têtes réservés.
2. Rejet explicite de `64:ff9b::/96`, `64:ff9b:1::/48`, `::/96` (IPv4-compatible),
   `2002::/16`, `192.88.99.0/24`, `is_multicast`, `is_reserved`, `is_unspecified` ;
   revalidation de toute IPv4 encapsulée.
3. Test de la posture TLS **par défaut** (sans contexte injecté).

**À trancher explicitement (ne pas laisser implicite)** — F-04 : router
`onmci_client` par le transport central, ou consigner par écrit son exclusion de
périmètre et le lien avec l'alerte CodeQL restante.

**Ensuite** — F-05 à F-10 en dette de sécurité suivie.

Une fois F-01/F-02/F-03 corrigés et leurs tests de régression ajoutés (chacun
devant tuer le mutant correspondant), je m'attends à un verdict SAFE_TO_PUSH.

P0_SSRF_RECOMMENDATION: NEEDS_FIX_BEFORE_PUSH
