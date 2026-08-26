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
