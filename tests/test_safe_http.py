"""Regression tests for the centralized SSRF-safe outbound HTTP transport."""

from __future__ import annotations

import socket
import ssl
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import critical_notifier, expiry_notifier, notifier
from app.utils import safe_http
from app.utils.safe_http import UnsafeOutboundUrlError


def _answer(ip: str, port: int = 80) -> tuple:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


@pytest.mark.parametrize(
    "url,ip",
    [
        ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
        ("http://100.64.0.1/hook", "100.64.0.1"),
        ("http://198.18.0.1/hook", "198.18.0.1"),
        ("http://192.0.0.1/hook", "192.0.0.1"),
        ("http://192.88.99.1/hook", "192.88.99.1"),
        ("http://224.0.0.1/hook", "224.0.0.1"),
        ("http://239.255.255.250/hook", "239.255.255.250"),
        ("http://[::1]/hook", "::1"),
        ("http://[fec0::1]/hook", "fec0::1"),
        ("http://[ff02::1]/hook", "ff02::1"),
        ("http://[::ffff:10.0.0.1]/hook", "::ffff:10.0.0.1"),
        ("http://[::7f00:1]/hook", "::7f00:1"),
        ("http://[64:ff9b::7f00:1]/hook", "64:ff9b::7f00:1"),
        ("http://[64:ff9b::a9fe:a9fe]/hook", "64:ff9b::a9fe:a9fe"),
        ("http://[64:ff9b:1::7f00:1]/hook", "64:ff9b:1::7f00:1"),
        ("http://[2002:7f00:1::]/hook", "2002:7f00:1::"),
    ],
)
def test_non_public_destinations_are_rejected_without_socket(url: str, ip: str) -> None:
    with (
        patch("app.utils.safe_http.socket.getaddrinfo", return_value=[_answer(ip)]),
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json(url, b"{}", timeout=1)
    socket_factory.assert_not_called()


def test_mixed_public_and_private_dns_answers_are_rejected() -> None:
    answers = [_answer("93.184.216.34"), _answer("10.0.0.8")]
    with (
        patch("app.utils.safe_http.socket.getaddrinfo", return_value=answers),
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json("http://mixed.example/hook", b"{}", timeout=1)
    socket_factory.assert_not_called()


def test_redirect_response_is_returned_and_never_followed() -> None:
    target = safe_http.ResolvedTarget(
        scheme="http",
        hostname="public.example",
        port=80,
        request_target="/hook",
        host_header="public.example",
        family=socket.AF_INET,
        socktype=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
        sockaddr=("93.184.216.34", 80),
    )
    response = MagicMock(status=302)
    response.getheader.return_value = "http://169.254.169.254/latest/meta-data/"
    connection = MagicMock()
    connection.getresponse.return_value = response
    with (
        patch("app.utils.safe_http.resolve_public_target", return_value=target),
        patch("app.utils.safe_http._connection_for", return_value=connection),
    ):
        status = safe_http.safe_post_json("http://public.example/hook", b"{}", timeout=1)

    assert status == 302
    connection.request.assert_called_once()
    assert connection.request.call_args.kwargs["headers"]["Host"] == "public.example"
    response.getheader.assert_not_called()


@pytest.mark.parametrize(
    "header_name",
    ["Host", "host", "HOST", "HoSt", "content-length", "Transfer-Encoding", "Connection", "Expect"],
)
def test_reserved_headers_are_rejected_case_insensitively(header_name: str) -> None:
    target = MagicMock(host_header="public.example")
    with (
        patch("app.utils.safe_http.resolve_public_target", return_value=target),
        patch("app.utils.safe_http._connection_for") as connection_factory,
    ):
        with pytest.raises(ValueError, match="Reserved outbound HTTP header"):
            safe_http.safe_post_json(
                "http://public.example/hook",
                b"{}",
                timeout=1,
                headers={header_name: "attacker.invalid"},
            )
    connection_factory.assert_not_called()


def test_connection_uses_validated_ip_without_second_dns_resolution() -> None:
    public = _answer("93.184.216.34")
    internal_rebind = _answer("10.0.0.7")
    with patch(
        "app.utils.safe_http.socket.getaddrinfo",
        side_effect=[[public], [internal_rebind]],
    ) as resolver:
        target = safe_http.resolve_public_target("http://rebind.example/hook")
        raw_socket = MagicMock()
        with patch("app.utils.safe_http.socket.socket", return_value=raw_socket):
            safe_http._PinnedHTTPConnection(target, timeout=1).connect()

    resolver.assert_called_once_with("rebind.example", 80, type=socket.SOCK_STREAM)
    raw_socket.connect.assert_called_once_with(("93.184.216.34", 80))


def test_https_connects_to_pinned_ip_and_preserves_tls_hostname() -> None:
    target = safe_http.ResolvedTarget(
        scheme="https",
        hostname="hooks.example.com",
        port=443,
        request_target="/notify",
        host_header="hooks.example.com",
        family=socket.AF_INET,
        socktype=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
        sockaddr=("93.184.216.34", 443),
    )
    raw_socket = MagicMock()
    tls_socket = MagicMock()
    context = MagicMock(spec=ssl.SSLContext)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.wrap_socket.return_value = tls_socket

    with patch("app.utils.safe_http.socket.socket", return_value=raw_socket):
        connection = safe_http._PinnedHTTPSConnection(target, timeout=2, context=context)
        connection.connect()

    raw_socket.connect.assert_called_once_with(("93.184.216.34", 443))
    context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="hooks.example.com")
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert connection.host == "hooks.example.com"


def test_https_default_context_requires_certificate_and_hostname_validation() -> None:
    target = safe_http.ResolvedTarget(
        scheme="https",
        hostname="hooks.example.com",
        port=443,
        request_target="/notify",
        host_header="hooks.example.com",
        family=socket.AF_INET,
        socktype=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
        sockaddr=("93.184.216.34", 443),
    )

    connection = safe_http._connection_for(target, timeout=2)

    assert isinstance(connection, safe_http._PinnedHTTPSConnection)
    assert connection._context.check_hostname is True
    assert connection._context.verify_mode == ssl.CERT_REQUIRED
    assert connection._context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert connection._context.get_ca_certs()


def test_all_three_notifiers_share_the_central_transport() -> None:
    assert notifier.safe_post_json is safe_http.safe_post_json
    assert critical_notifier.safe_post_json is safe_http.safe_post_json
    assert expiry_notifier.safe_post_json is safe_http.safe_post_json


def test_critical_notifier_calls_central_transport() -> None:
    with patch("app.services.critical_notifier.safe_post_json", return_value=204) as post:
        assert critical_notifier._send_webhook("https://hooks.example/hook", {"ok": True})
    post.assert_called_once()


def test_expiry_notifier_calls_central_transport() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(webhook_url="https://hooks.example/expiry")
    ]
    expiring = [{"id": 1, "name": "R", "expiry_date": "2026-09-01"}]
    with (
        patch("app.services.expiry_notifier.get_expiring_reagents", return_value=expiring),
        patch("app.services.expiry_notifier.safe_post_json", return_value=200) as post,
    ):
        result = expiry_notifier.check_and_notify_expiry(db)

    assert result == {"notified": 1, "expiring": 1}
    post.assert_called_once()


# ---------------------------------------------------------------------------
# F-01 closure matrix — cases required by the remediation instruction that the
# initial suite did not cover explicitly.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,ip",
    [
        # 127.0.0.0/8 — the exact address reached by the original proof of concept
        ("http://127.0.0.1/interne/admin", "127.0.0.1"),
        ("http://127.0.0.53:8000/hook", "127.0.0.53"),
        ("http://127.255.255.254/hook", "127.255.255.254"),
        # RFC 1918
        ("http://10.0.0.1/hook", "10.0.0.1"),
        ("http://172.16.0.1/hook", "172.16.0.1"),
        ("http://172.31.255.254/hook", "172.31.255.254"),
        ("http://192.168.1.1/hook", "192.168.1.1"),
        # IPv4 link-local beyond the cloud metadata address
        ("http://169.254.1.1/hook", "169.254.1.1"),
        # Unspecified address
        ("http://0.0.0.0/hook", "0.0.0.0"),
        # IPv6 link-local and unique-local
        ("http://[fe80::1]/hook", "fe80::1"),
        ("http://[fd00::1]/hook", "fd00::1"),
        # Compose service address reachable from the app container
        ("http://172.18.0.2:5432/hook", "172.18.0.2"),
    ],
)
def test_literal_private_destinations_are_rejected_without_socket(url: str, ip: str) -> None:
    """No literal private, loopback, link-local or unspecified address is dialled."""
    with (
        patch("app.utils.safe_http.socket.getaddrinfo", return_value=[_answer(ip)]),
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json(url, b"{}", timeout=1)
    socket_factory.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://93.184.216.34/_x",
        "data:text/plain,hello",
        "ws://example.com/socket",
        "//example.com/schemeless",
        "not a url",
        "",
    ],
)
def test_non_http_schemes_are_rejected_before_any_resolution(url: str) -> None:
    """Only http and https reach the resolver; everything else stops at parsing."""
    with (
        patch("app.utils.safe_http.socket.getaddrinfo") as resolver,
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json(url, b"{}", timeout=1)
    resolver.assert_not_called()
    socket_factory.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://[::1",
        "http://example.com:99999/x",
        "http://",
        "https://",
    ],
)
def test_malformed_urls_are_rejected_before_any_resolution(url: str) -> None:
    """A URL that cannot be parsed is refused, never handed to the resolver."""
    with (
        patch("app.utils.safe_http.socket.getaddrinfo") as resolver,
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json(url, b"{}", timeout=1)
    resolver.assert_not_called()
    socket_factory.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@hooks.example/x",  # pragma: allowlist secret
        "http://user@hooks.example/x",
        "https://:pass@hooks.example/x",  # pragma: allowlist secret
    ],
)
def test_url_userinfo_is_rejected_before_any_resolution(url: str) -> None:
    """Embedded credentials are never forwarded — the URL is refused outright."""
    with (
        patch("app.utils.safe_http.socket.getaddrinfo") as resolver,
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json(url, b"{}", timeout=1)
    resolver.assert_not_called()
    socket_factory.assert_not_called()


def test_ipv6_zone_identifier_is_rejected_before_any_resolution() -> None:
    """A zone identifier scopes the address to a local interface — always refused."""
    with (
        patch("app.utils.safe_http.socket.getaddrinfo") as resolver,
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json("http://[fe80::1%25eth0]/hook", b"{}", timeout=1)
    resolver.assert_not_called()
    socket_factory.assert_not_called()


@pytest.mark.parametrize(
    "hostname,ip",
    [
        ("localhost", "127.0.0.1"),
        ("postgres", "172.18.0.2"),
        ("metadata.google.internal", "169.254.169.254"),
        ("attacker-controlled.example", "10.1.2.3"),
    ],
)
def test_hostname_resolving_to_private_address_is_rejected(hostname: str, ip: str) -> None:
    """A hostname is judged on what it resolves to, not on how it reads."""
    with (
        patch("app.utils.safe_http.socket.getaddrinfo", return_value=[_answer(ip)]),
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json(f"http://{hostname}/hook", b"{}", timeout=1)
    socket_factory.assert_not_called()


def test_unresolvable_hostname_is_rejected_rather_than_dialled() -> None:
    """Resolution failure means the target cannot be proven public — fail closed."""
    with (
        patch(
            "app.utils.safe_http.socket.getaddrinfo",
            side_effect=socket.gaierror("Name or service not known"),
        ),
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json("http://nowhere.invalid/hook", b"{}", timeout=1)
    socket_factory.assert_not_called()


def test_empty_resolution_answer_is_rejected() -> None:
    """An empty answer set proves nothing about the destination — fail closed."""
    with (
        patch("app.utils.safe_http.socket.getaddrinfo", return_value=[]),
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json("http://empty.example/hook", b"{}", timeout=1)
    socket_factory.assert_not_called()


def test_validation_runs_at_transport_call_time_not_at_schema_level() -> None:
    """The request schema accepts any string; the transport is what refuses it.

    Guards F-01 against a regression where validation is moved back up to the
    Pydantic layer only — an internal caller would then bypass it entirely.
    """
    from app.schemas.notification import NotificationRequest

    request = NotificationRequest.model_validate(
        {
            "drugs": [],
            "horizon_days": 90,
            "channel": "WEBHOOK",
            "severity_filter": "TOUTES",
            "webhook_url": "http://169.254.169.254/latest/meta-data/",
        }
    )
    # The schema itself does not reject the address.
    assert request.webhook_url == "http://169.254.169.254/latest/meta-data/"

    with (
        patch(
            "app.utils.safe_http.socket.getaddrinfo",
            return_value=[_answer("169.254.169.254")],
        ),
        patch("app.utils.safe_http.socket.socket") as socket_factory,
    ):
        with pytest.raises(UnsafeOutboundUrlError):
            safe_http.safe_post_json(request.webhook_url, b"{}", timeout=1)
    socket_factory.assert_not_called()


def test_public_destination_is_still_reachable() -> None:
    """The guard must not break the legitimate case it exists to protect."""
    raw_socket = MagicMock()
    with (
        patch(
            "app.utils.safe_http.socket.getaddrinfo",
            return_value=[_answer("93.184.216.34")],
        ),
        patch("app.utils.safe_http.socket.socket", return_value=raw_socket),
        patch.object(safe_http._PinnedHTTPConnection, "request", return_value=None),
        patch.object(
            safe_http._PinnedHTTPConnection,
            "getresponse",
            return_value=MagicMock(status=202),
        ),
    ):
        status = safe_http.safe_post_json("http://hooks.example/notify", b"{}", timeout=1)

    assert status == 202


@pytest.mark.parametrize(
    "refused_version",
    [ssl.TLSVersion.SSLv3, ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1_1],
)
def test_default_tls_context_refuses_obsolete_protocol_versions(
    refused_version: ssl.TLSVersion,
) -> None:
    """Le plancher TLS est fixé dans le code, pas laissé à la config OpenSSL locale."""
    context = safe_http._default_tls_context()

    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert context.minimum_version > refused_version
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
