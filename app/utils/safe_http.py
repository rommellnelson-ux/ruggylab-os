"""Outbound HTTP transport with SSRF-safe, DNS-pinned connections."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

_ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_PORTS = {"http": 80, "https": 443}
_MAX_REQUEST_BODY_BYTES = 1_048_576
_RESERVED_REQUEST_HEADERS = {
    "connection",
    "content-length",
    "expect",
    "host",
    "transfer-encoding",
}
_IPV4_RELAY_ANYCAST = ipaddress.ip_network("192.88.99.0/24")
_IPV6_IPV4_COMPATIBLE = ipaddress.ip_network("::/96")
_IPV6_NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")
_IPV6_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_IPV6_6TO4 = ipaddress.ip_network("2002::/16")


class UnsafeOutboundUrlError(ValueError):
    """Raised when an outbound destination cannot be proven public and safe."""


@dataclass(frozen=True)
class ResolvedTarget:
    scheme: str
    hostname: str
    port: int
    request_target: str
    host_header: str
    family: int
    socktype: int
    proto: int
    sockaddr: tuple


def _is_public_address(value: str) -> bool:
    """Allow only addresses suitable for direct public Internet routing."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return address not in _IPV4_RELAY_ANYCAST
    if address.is_site_local:
        return False
    if address.ipv4_mapped is not None:
        return _is_public_address(str(address.ipv4_mapped))
    return not any(
        address in network
        for network in (
            _IPV6_IPV4_COMPATIBLE,
            _IPV6_NAT64_WELL_KNOWN,
            _IPV6_NAT64_LOCAL,
            _IPV6_6TO4,
        )
    )


def _host_header(parsed: SplitResult, hostname: str, port: int) -> str:
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    if port == _DEFAULT_PORTS[parsed.scheme]:
        return rendered_host
    return f"{rendered_host}:{port}"


def resolve_public_target(url: str) -> ResolvedTarget:
    """Parse and resolve once, rejecting the target if any answer is non-public."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise UnsafeOutboundUrlError("Malformed outbound URL") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeOutboundUrlError("Only HTTP and HTTPS are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeOutboundUrlError("URL userinfo is forbidden")
    hostname = parsed.hostname
    if not hostname or "%" in hostname:
        raise UnsafeOutboundUrlError("A hostname without a zone identifier is required")
    port = port or _DEFAULT_PORTS[parsed.scheme]

    try:
        answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise UnsafeOutboundUrlError("Destination resolution failed") from exc
    if not answers:
        raise UnsafeOutboundUrlError("Destination returned no addresses")

    validated: list[tuple[socket.AddressFamily, socket.SocketKind, int, tuple]] = []
    for family, socktype, proto, _canonname, sockaddr in answers:
        if family not in {socket.AF_INET, socket.AF_INET6} or socktype != socket.SOCK_STREAM:
            raise UnsafeOutboundUrlError("Unsupported destination address family")
        if not _is_public_address(str(sockaddr[0])):
            raise UnsafeOutboundUrlError("Destination contains a non-public address")
        validated.append((family, socktype, proto, sockaddr))

    family, socktype, proto, sockaddr = validated[0]
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return ResolvedTarget(
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        request_target=request_target,
        host_header=_host_header(parsed, hostname, port),
        family=family,
        socktype=socktype,
        proto=proto,
        sockaddr=sockaddr,
    )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, target: ResolvedTarget, timeout: float) -> None:
        super().__init__(target.hostname, target.port, timeout=timeout)
        self._target = target

    def _connect_validated_socket(self) -> socket.socket:
        sock = socket.socket(self._target.family, self._target.socktype, self._target.proto)
        try:
            sock.settimeout(self.timeout)
            sock.connect(self._target.sockaddr)
        except Exception:
            sock.close()
            raise
        return sock

    def connect(self) -> None:
        self.sock = self._connect_validated_socket()


class _PinnedHTTPSConnection(_PinnedHTTPConnection):
    def __init__(
        self,
        target: ResolvedTarget,
        timeout: float,
        context: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(target, timeout)
        self._context = context or ssl.create_default_context()

    def connect(self) -> None:
        raw_socket = self._connect_validated_socket()
        try:
            self.sock = self._context.wrap_socket(
                raw_socket,
                server_hostname=self._target.hostname,
            )
        except Exception:
            raw_socket.close()
            raise


def _connection_for(target: ResolvedTarget, timeout: float) -> _PinnedHTTPConnection:
    if target.scheme == "https":
        return _PinnedHTTPSConnection(target, timeout)
    return _PinnedHTTPConnection(target, timeout)


def safe_post_json(
    url: str,
    body: bytes,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> int:
    """POST once to a validated pinned address; redirects are never followed."""
    if len(body) > _MAX_REQUEST_BODY_BYTES:
        raise ValueError("Outbound request body exceeds the 1 MiB limit")
    target = resolve_public_target(url)
    caller_headers = headers or {}
    forbidden = _RESERVED_REQUEST_HEADERS.intersection(name.lower() for name in caller_headers)
    if forbidden:
        raise ValueError(f"Reserved outbound HTTP header: {sorted(forbidden)[0]}")
    request_headers = {
        **caller_headers,
        "Content-Type": "application/json",
        "Host": target.host_header,
    }
    connection = _connection_for(target, timeout)
    try:
        connection.request("POST", target.request_target, body=body, headers=request_headers)
        response = connection.getresponse()
        try:
            return response.status
        finally:
            response.close()
    finally:
        connection.close()
