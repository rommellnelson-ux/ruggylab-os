"""Tests du listener TCP brut (capture aveugle -> Redis) et des parseurs.

Le listener ne doit rien parser : on vérifie le découpage protocole-agnostique
des trames, la fidélité octet à octet du payload Redis, la survie aux coupures
brutales de socket, et le contrat des abstractions parseurs.
"""

import asyncio
import base64
import contextlib
import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from app.services.analyzers import (
    AnalyzerParserFactory,
    AnalyzerResultBase,
    BaseAnalyzerParser,
    DymindDH36Parser,
    DymindHematologyParser,
)
from app.services.analyzers.registry import AnalyzerBinding, AnalyzerKind, enabled_bindings
from app.services.interfacing.raw_tcp_listener import (
    ASCII_ACK,
    RawAnalyzerTCPListener,
    build_frame_payload,
    split_frames,
)

MLLP_FRAME = b"\x0bMSH|^~\\&|DH36|DYMIND|RUGGYLAB|LAB|20260708||ORU^R01|42||2.3.1\r\x1c\x0d"
ASTM_FRAME = b"\x021H|\\^&|||DH36\x03A7\r\n\x04"


# ── split_frames ──────────────────────────────────────────────────────────────


def test_split_frames_mllp() -> None:
    frames, rest = split_frames(MLLP_FRAME + b"partiel")
    assert frames == [(MLLP_FRAME, "mllp-end")]
    assert rest == b"partiel"


def test_split_frames_astm_eot() -> None:
    frames, rest = split_frames(ASTM_FRAME)
    assert frames == [(ASTM_FRAME, "astm-eot")]
    assert rest == b""


def test_split_frames_mixed_order_preserved() -> None:
    frames, rest = split_frames(MLLP_FRAME + ASTM_FRAME + MLLP_FRAME[:10])
    assert [hint for _, hint in frames] == ["mllp-end", "astm-eot"]
    assert rest == MLLP_FRAME[:10]


def test_split_frames_incomplete_returns_everything_as_rest() -> None:
    frames, rest = split_frames(b"pas de terminateur ici")
    assert frames == []
    assert rest == b"pas de terminateur ici"


# ── build_frame_payload ───────────────────────────────────────────────────────


def test_build_frame_payload_is_lossless_and_annotated() -> None:
    raw = b"\x0bMSH|donnees\xff binaires\x1c\x0d"
    doc = json.loads(
        build_frame_payload(
            raw,
            analyzer_kind="dymind_hematology",
            listener_port=9000,
            delimiter_hint="mllp-end",
            source_ip="10.0.30.5",
            source_port=4321,
        )
    )
    assert base64.b64decode(doc["frame_b64"]) == raw
    assert doc["sha256"] == hashlib.sha256(raw).hexdigest()
    assert doc["analyzer_kind"] == "dymind_hematology"
    assert doc["port"] == 9000
    assert doc["source_ip"] == "10.0.30.5"
    assert doc["source_port"] == 4321
    assert doc["delimiter"] == "mllp-end"
    assert doc["bytes"] == len(raw)
    assert doc["raw_payload"] == raw.decode("utf-8", errors="replace")
    # Clés exigées par la spec.
    assert {"timestamp", "source_ip", "port", "raw_payload"} <= doc.keys()


# ── Listener bout en bout (sans Redis : on capture les payloads en mémoire) ──


def _make_listener(**overrides: object) -> tuple[RawAnalyzerTCPListener, list[tuple[bytes, str]]]:
    listener = RawAnalyzerTCPListener(
        host="127.0.0.1",
        port=0,
        redis_url="redis://localhost:6379/0",
        idle_timeout_seconds=5.0,
        **overrides,  # type: ignore[arg-type]
    )
    stored: list[tuple[bytes, str]] = []

    async def _capture(frame: bytes, hint: str, ip: str, port: int) -> None:
        stored.append((frame, hint))

    listener._store_frame = _capture  # type: ignore[method-assign]
    return listener, stored


async def _serve(listener: RawAnalyzerTCPListener) -> tuple[asyncio.Server, int]:
    server = await asyncio.start_server(listener._handle_client, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_listener_acks_and_stores_frames() -> None:
    async def scenario() -> None:
        listener, stored = _make_listener()
        server, port = await _serve(listener)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(MLLP_FRAME + ASTM_FRAME)
            await writer.drain()
            ack = await asyncio.wait_for(reader.readexactly(2), timeout=5)
            assert ack == ASCII_ACK + ASCII_ACK
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()
        assert [hint for _, hint in stored] == ["mllp-end", "astm-eot"]
        assert stored[0][0] == MLLP_FRAME

    asyncio.run(scenario())


def test_listener_flushes_partial_frame_on_abrupt_disconnect() -> None:
    async def scenario() -> None:
        listener, stored = _make_listener(ack_mode="silent")
        server, port = await _serve(listener)
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"trame tronquee sans terminateur")
            await writer.drain()
            writer.transport.abort()  # coupure brutale, sans FIN propre
            for _ in range(50):
                if stored:
                    break
                await asyncio.sleep(0.05)
        finally:
            server.close()
            await server.wait_closed()
        assert stored == [(b"trame tronquee sans terminateur", "eof-flush")]

    asyncio.run(scenario())


def test_listener_close_mode_disconnects_after_first_frame() -> None:
    async def scenario() -> None:
        listener, stored = _make_listener(ack_mode="close")
        server, port = await _serve(listener)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(MLLP_FRAME)
            await writer.drain()
            eof = await asyncio.wait_for(reader.read(16), timeout=5)
            assert eof == b""  # la passerelle a fermé proprement
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()
        assert [hint for _, hint in stored] == ["mllp-end"]

    asyncio.run(scenario())


def test_listener_rejects_unknown_ack_mode() -> None:
    with pytest.raises(ValueError, match="ack_mode"):
        RawAnalyzerTCPListener(
            host="127.0.0.1", port=0, redis_url="redis://localhost", ack_mode="bogus"
        )


def test_listener_rejects_ip_outside_allowlist() -> None:
    async def scenario() -> None:
        listener, stored = _make_listener(ack_mode="silent", allowed_ips=["10.0.30.9"])
        server, port = await _serve(listener)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(MLLP_FRAME)
            await writer.drain()
            # La connexion 127.0.0.1 n'est pas dans l'allowlist : le serveur ferme
            # immédiatement. Selon l'OS : EOF vide (POSIX) ou reset (Windows).
            with contextlib.suppress(ConnectionResetError):
                eof = await asyncio.wait_for(reader.read(16), timeout=5)
                assert eof == b""
            writer.close()
            with contextlib.suppress(ConnectionResetError):
                await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()
        assert stored == []

    asyncio.run(scenario())


# ── Registry & Factory ────────────────────────────────────────────────────────


def test_enabled_bindings_default_ports_are_distinct() -> None:
    from app.core.config import Settings

    bindings = enabled_bindings(Settings())
    kinds = {b.kind for b in bindings}
    ports = [b.port for b in bindings]
    assert kinds == {AnalyzerKind.HEMATOLOGY, AnalyzerKind.BIOCHEMISTRY, AnalyzerKind.IMMUNO}
    assert sorted(ports) == [9000, 9001, 9002]
    assert len(ports) == len(set(ports))


def test_enabled_bindings_detects_port_collision() -> None:
    from app.core.config import Settings

    settings = Settings(ANALYZER_BIOCHEMISTRY_PORT=9000)  # collision avec hémato
    with pytest.raises(ValueError, match="port"):
        enabled_bindings(settings)


def test_factory_returns_parser_per_kind() -> None:
    assert isinstance(
        AnalyzerParserFactory.get_parser(AnalyzerKind.HEMATOLOGY), DymindHematologyParser
    )
    # Accepte aussi la valeur brute lue dans le JSON Redis.
    parser = AnalyzerParserFactory.get_parser("anbio_immuno")
    assert parser.analyzer_model == "Anbio Bioscann"
    assert set(AnalyzerParserFactory.supported_kinds()) == set(AnalyzerKind)


def test_factory_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        AnalyzerParserFactory.get_parser("automate_inconnu")


def test_binding_is_frozen() -> None:
    binding = AnalyzerBinding(kind=AnalyzerKind.HEMATOLOGY, host="127.0.0.1", port=9000)
    with pytest.raises(FrozenInstanceError):
        binding.port = 9999  # type: ignore[misc]


# ── Abstractions parseurs ─────────────────────────────────────────────────────


def test_base_parser_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseAnalyzerParser()  # type: ignore[abstract]


def test_dymind_parser_not_implemented_yet() -> None:
    # DymindDH36Parser est un alias de rétrocompat vers DymindHematologyParser.
    parser = DymindDH36Parser()
    assert isinstance(parser, DymindHematologyParser)
    assert parser.analyzer_model == "Dymind DH36"
    with pytest.raises(NotImplementedError, match="manuel d'interfaçage"):
        parser.parse("MSH|^~\\&|...")


def test_analyzer_result_base_defaults() -> None:
    result = AnalyzerResultBase(analyzer_model="Dymind DH36")
    assert result.protocol == "unknown"
    assert result.parameters == {}
    assert result.flags == {}
    assert result.sample_barcode is None
