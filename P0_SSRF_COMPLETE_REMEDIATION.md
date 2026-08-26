# P0 SSRF Complete Remediation

Audit target: `061b102776f6254309d321dec86b4819dd9e375d` plus the local remediation
described below. This document does not claim that the GitHub CodeQL alert is closed.

## A. Original vulnerability

`POST /api/v1/stock/notify` accepted a caller-provided webhook URL and passed it to
`urllib.request.urlopen`. Any authenticated user could make the server contact an
arbitrary destination, including internal services and cloud metadata endpoints.

## B. Claude bypass findings

The first patch validated only the initial URL. Independent review demonstrated two
remaining bypasses:

- `P0-SSRF-01`: urllib followed redirects without validating the redirect target.
- `P0-SSRF-03`: validation resolved DNS once, but the later connection resolved the
  hostname again, allowing DNS rebinding between validation and use.

The review also identified that `100.64.0.0/10` (CGNAT/shared space) was accepted.

## C. Root cause

URL policy and network connection were separate operations. The validated DNS result
was discarded, redirects were delegated to a client with automatic redirect handling,
and the three notifier implementations had diverging HTTP logic.

## D. Architecture of the new outbound transport

`app/utils/safe_http.py` is the single outbound webhook primitive. It parses and
resolves the URL, validates every DNS answer, retains a selected validated socket
address, creates a socket using that address, and performs one HTTP POST. It uses only
the Python standard library; no dependency was added.

The request body is capped at 1 MiB. Resolver, parser, socket, TLS, and protocol errors
fail closed and are handled by notifier callers as failed delivery.

## E. DNS resolution policy

The hostname is resolved exactly once with `socket.getaddrinfo(..., SOCK_STREAM)`.
Every returned IPv4 or IPv6 address must pass the public-address policy. A mixed result
containing one public and one forbidden address is rejected. The first validated
`sockaddr` is retained and used directly by `socket.connect`; the hostname is not
resolved again for the connection.

## F. Redirect policy

Redirects are disabled. The transport uses `http.client`, which performs no automatic
redirect handling. A 3xx status is returned to the notifier and is treated as failed
delivery. The `Location` header is not consumed and no second request is issued.

## G. TLS/SNI handling

HTTPS connects the raw socket to the validated numeric IP, then wraps it with
`ssl.create_default_context()`. The original hostname is passed as `server_hostname`,
preserving SNI and certificate hostname verification. TLS verification is not disabled.
The original hostname is forced into the HTTP `Host` header and cannot be overridden by
caller-supplied headers.

## H. IP-address policy

Only addresses for which `ipaddress.ip_address(...).is_global` is true are accepted,
with explicit deny rules for multicast, IPv4 relay anycast (`192.88.99.0/24`),
IPv4-compatible IPv6 (`::/96`), well-known and local NAT64 prefixes
(`64:ff9b::/96`, `64:ff9b:1::/48`), and 6to4 (`2002::/16`). IPv4-mapped IPv6
addresses must also pass the IPv4 policy. This rejects loopback, private, link-local,
reserved/non-global, unspecified, multicast, CGNAT/shared space, and the explicitly
listed transition ranges. If any DNS answer is forbidden, the complete target is
rejected.

## I. User-controlled outbound webhook call sites

The centralized `safe_post_json` primitive is used by:

- `app/services/notifier.py` — stock notifications;
- `app/services/critical_notifier.py` — unacknowledged critical results;
- `app/services/expiry_notifier.py` — reagent expiry notifications.

This centralization claim is limited to webhook destinations influenced by request or
application data. `app/services/onmci_client.py` remains explicitly out of scope because
its base destination comes only from server configuration. It is not the dataflow of
CodeQL alert 11, which concerned the stock notifier. This is a scope decision, not proof
that the ONMCI client has undergone a complete outbound-network security review.

## J. Tests added

`tests/test_safe_http.py` covers:

- direct cloud metadata/link-local rejection with zero socket creation;
- redirect response not followed and `Location` not read;
- DNS rebinding simulation and connection to the retained public IP;
- mixed public/private DNS rejection;
- CGNAT rejection;
- IPv6 loopback rejection;
- IPv4-mapped private IPv6 rejection;
- HTTPS connection to the pinned IP with original hostname as SNI;
- certificate verification context expectations;
- forced original `Host` header;
- case-insensitive rejection of caller-supplied `Host`, `Content-Length`,
  `Transfer-Encoding`, `Connection`, and `Expect` headers;
- IPv4/IPv6 multicast, relay-anycast, IPv4-compatible, NAT64 and 6to4 rejection;
- all three notifier integrations with the centralized primitive.

Existing stock notifier tests were adapted to mock the centralized transport rather than
`urllib.request.urlopen`.

## K. Mutation test results

Two temporary vulnerable mutations were introduced and immediately restored:

1. Redirect-follow mutation: the redirect regression test failed because two requests
   were observed instead of one.
2. Unpinned-destination mutation: the rebinding regression test failed because the
   socket received `('rebind.example', 80)` instead of `('93.184.216.34', 80)`.

No intentionally vulnerable mutation remains in the worktree.

## L. Commands executed

```text
python -m pytest tests/test_safe_http.py tests/test_stock_notifications.py --tb=short -q
python -m pytest tests/test_safe_http.py::test_redirect_response_is_returned_and_never_followed --tb=short -q
python -m pytest tests/test_safe_http.py::test_connection_uses_validated_ip_without_second_dns_resolution --tb=short -q
python -m pytest tests/test_safe_http.py tests/test_stock_notifications.py tests/test_critical_notifier.py tests/test_expiry_and_amend.py tests/test_notifications.py tests/test_security_hardening.py --tb=short -q
python -m ruff check app tests
python -m ruff format --check app tests
python -m bandit -q -r app -c pyproject.toml
git diff --check
```

## M. Results

- Focused transport suite after final-review reconciliation: `32 passed in 1.39s`.
- Final relevant notifier/security suite after final-review reconciliation: `117 passed
  in 137.08s`.
- Larger auth/API regression suite (`scripts/validate.ps1 -Fast`): `30 passed in
  79.90s`.
- Redirect mutation: expected failure, two requests observed.
- Destination-pinning mutation: expected failure, hostname connection observed.
- Ruff: pass.
- Ruff format check: pass.
- Bandit: pass.
- `git diff --check`: pass.
- Dependency audit remains failed independently of this remediation: 20 reported
  occurrences against Pillow 12.2.0. The local validation script does not propagate
  that intermediate failure and ended with code 0.

## N. Remaining limitations

- The GitHub CodeQL alert remains open until the change is pushed and CodeQL reruns.
- No proxy support or redirect allowlist is provided; both are intentionally absent.
- A single validated address is selected; the transport does not retry alternative DNS
  answers after connection failure.
- Network-layer egress controls remain recommended as defense in depth.
- This remediation does not change the configuration-controlled ONMCI client.
- Port allowlisting and restricting `/stock/notify` to officer/admin roles remain product
  policy decisions; they are not required for destination integrity and were not changed.

### Independent-review reconciliation

`CLAUDE_P0_SSRF_REVIEW.md` reviewed the superseded three-line guard patch, not the
centralized pinned transport. Its confirmed redirect and DNS-rebinding findings are
closed by the current local implementation and regression tests.

`CLAUDE_FINAL_SSRF_REVIEW.md` then reviewed the pinned transport. Its F-01 through F-03
findings were incorporated: reserved request headers are rejected case-insensitively,
additional transition/special-use address families are explicitly rejected, and a test
now inspects the real default TLS context. F-04 was resolved as the explicit ONMCI scope
decision documented above. Deprecated IPv6 site-local space is also explicitly rejected,
and failed webhook responses no longer echo the submitted URL. Another independent
review of this final local diff is still required.

## O. Exact diff summary

Security-remediation files:

- added `app/utils/safe_http.py`: 203 lines;
- modified `app/services/notifier.py`: +12/-26;
- modified `app/services/critical_notifier.py`: +3/-17;
- modified `app/services/expiry_notifier.py`: +13/-15;
- added `tests/test_safe_http.py`: 206 lines;
- modified `tests/test_stock_notifications.py`: +24/-28;
- added `P0_SSRF_COMPLETE_REMEDIATION.md` (this report; line count changes with this
  final update).

Pre-existing user changes in `.env.example`, `docker-compose.yml`,
`PLAN_AMELIORATION.md`, `CLAUDE_P0_SSRF_REVIEW.md`, and
`CLAUDE_FINAL_SSRF_REVIEW.md` were not modified as part of this remediation.

## Status

`P0_SSRF_STATUS: READY_FOR_INDEPENDENT_REVIEW`
