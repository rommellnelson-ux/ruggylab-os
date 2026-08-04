#!/usr/bin/env python3
r"""Simulateur de charge Dymind DH36 — trames factices HL7 (MLLP) et ASTM.

Script autonome (stdlib uniquement, aucune dépendance à l'application) qui
ouvre des connexions TCP vers l'analyzer-gateway, envoie des trames NFS
aléatoires, lit l'ACK éventuel, ferme, et recommence toutes les X secondes.
Sert à valider la robustesse de l'ingestion Redis (fuites mémoire, coupures,
reconnexions) avant l'arrivée du vrai automate.

Exemples :
    python scripts/mock_dymind.py                       # HL7+ASTM, toutes les 2 s
    python scripts/mock_dymind.py --protocol astm --interval 0.5 --burst 5
    python scripts/mock_dymind.py --port 9000 --count 100 --abort-ratio 0.1

``--abort-ratio`` coupe brutalement un pourcentage de connexions en pleine
trame (sans délimiteur final) pour tester le chemin ``eof-flush`` du listener.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import logging
import random
import string
import sys

logger = logging.getLogger("mock_dymind")

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"
ASTM_STX = b"\x02"
ASTM_ETX = b"\x03"
ASTM_EOT = b"\x04"
ASTM_ENQ = b"\x05"
CR = b"\x0d"

# Plages plausibles (incluant des valeurs paniques) pour une NFS DH36.
NFS_PARAMS: dict[str, tuple[float, float, str]] = {
    "WBC": (1.0, 25.0, "10*9/L"),
    "RBC": (2.0, 7.0, "10*12/L"),
    "HGB": (50.0, 190.0, "g/L"),
    "HCT": (15.0, 60.0, "%"),
    "MCV": (55.0, 115.0, "fL"),
    "MCH": (18.0, 40.0, "pg"),
    "MCHC": (270.0, 390.0, "g/L"),
    "PLT": (20.0, 700.0, "10*9/L"),
}


def _random_id(length: int = 8) -> str:
    return "".join(random.choices(string.digits, k=length))


def _random_results() -> dict[str, float]:
    return {name: round(random.uniform(lo, hi), 2) for name, (lo, hi, _unit) in NFS_PARAMS.items()}


def build_hl7_frame() -> bytes:
    """Construit un message ORU^R01 factice encadré MLLP, façon automate hémato."""
    now = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    control_id = _random_id(10)
    ipp = f"IPP{_random_id(6)}"
    barcode = f"SMP{_random_id(8)}"
    segments = [
        f"MSH|^~\\&|DH36-{_random_id(4)}|DYMIND|RUGGYLAB|LAB|{now}||ORU^R01|{control_id}||2.3.1",
        f"PID|1|{ipp}|{ipp}||MOCK^PATIENT||19900101|{random.choice('MF')}",
        f"OBR|1|{barcode}|{barcode}|NFS^Numeration Formule Sanguine|||{now}",
    ]
    for idx, (name, value) in enumerate(_random_results().items(), start=1):
        unit = NFS_PARAMS[name][2]
        segments.append(f"OBX|{idx}|NM|{name}^{name}||{value}|{unit}||N|||F")
    payload = "\r".join(segments).encode("ascii")
    return MLLP_START + payload + CR + MLLP_END


def _astm_checksum(body: bytes) -> bytes:
    """Checksum ASTM E1381 : somme modulo 256 en 2 chiffres hexadécimaux."""
    return f"{sum(body) % 256:02X}".encode("ascii")


def build_astm_frames() -> list[bytes]:
    """Construit une session ASTM factice : ENQ, enregistrements H/P/O/R/L, EOT."""
    barcode = f"SMP{_random_id(8)}"
    now = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    records = [
        f"H|\\^&|||DH36^Dymind^{_random_id(4)}|||||||P|E1394-97|{now}",
        f"P|1||IPP{_random_id(6)}|||MOCK^PATIENT||19900101|{random.choice('MF')}",
        f"O|1|{barcode}||^^^NFS|R||{now}",
    ]
    for idx, (name, value) in enumerate(_random_results().items(), start=1):
        unit = NFS_PARAMS[name][2]
        records.append(f"R|{idx}|^^^{name}|{value}|{unit}||N||F||{now}")
    records.append("L|1|N")

    frames: list[bytes] = [ASTM_ENQ]
    for seq, record in enumerate(records, start=1):
        body = f"{seq % 8}{record}".encode("ascii") + ASTM_ETX
        frames.append(ASTM_STX + body + _astm_checksum(body) + CR + b"\x0a")
    frames.append(ASTM_EOT)
    return frames


async def send_session(
    host: str,
    port: int,
    frames: list[bytes],
    *,
    wait_ack: bool,
    ack_timeout: float,
    abort_midway: bool,
) -> tuple[int, int]:
    """Ouvre une connexion, envoie les trames, lit les ACK, ferme.

    Retourne (trames envoyées, octets envoyés).
    """
    reader, writer = await asyncio.open_connection(host, port)
    sent_frames = 0
    sent_bytes = 0
    try:
        for i, frame in enumerate(frames):
            if abort_midway and i == len(frames) // 2:
                # Coupure brutale volontaire : trame tronquée sans délimiteur.
                writer.write(frame[: max(1, len(frame) // 2)])
                await writer.drain()
                writer.transport.abort()
                logger.info("Connexion avortée volontairement en pleine trame (test eof-flush)")
                return sent_frames, sent_bytes
            writer.write(frame)
            await writer.drain()
            sent_frames += 1
            sent_bytes += len(frame)
            if wait_ack:
                with contextlib.suppress(TimeoutError):
                    ack = await asyncio.wait_for(reader.read(64), timeout=ack_timeout)
                    if ack:
                        logger.debug("ACK reçu: %r", ack)
                    else:
                        logger.info("Connexion fermée par la passerelle (mode close ?)")
                        return sent_frames, sent_bytes
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
    return sent_frames, sent_bytes


async def run_loop(args: argparse.Namespace) -> None:
    sessions_ok = 0
    sessions_ko = 0
    total_frames = 0
    total_bytes = 0
    iteration = 0

    while args.count == 0 or iteration < args.count:
        iteration += 1
        protocol = args.protocol if args.protocol != "mixed" else random.choice(["hl7", "astm"])
        frames: list[bytes] = []
        for _ in range(args.burst):
            if protocol == "hl7":
                frames.append(build_hl7_frame())
            else:
                frames.extend(build_astm_frames())
        abort_midway = random.random() < args.abort_ratio

        try:
            sent_frames, sent_bytes = await send_session(
                args.host,
                args.port,
                frames,
                wait_ack=not args.no_ack_wait,
                ack_timeout=args.ack_timeout,
                abort_midway=abort_midway,
            )
            sessions_ok += 1
            total_frames += sent_frames
            total_bytes += sent_bytes
            logger.info(
                "Session #%d %s ok: %d trame(s), %d octets",
                iteration,
                protocol.upper(),
                sent_frames,
                sent_bytes,
            )
        except (ConnectionRefusedError, ConnectionResetError, OSError) as exc:
            sessions_ko += 1
            logger.error("Session #%d KO (%s) — la passerelle écoute-t-elle ?", iteration, exc)

        if iteration % 10 == 0:
            logger.info(
                "Bilan: %d ok / %d ko, %d trames, %.1f Ko envoyés",
                sessions_ok,
                sessions_ko,
                total_frames,
                total_bytes / 1024,
            )
        await asyncio.sleep(args.interval)

    logger.info(
        "Terminé: %d session(s) ok, %d ko, %d trame(s), %.1f Ko",
        sessions_ok,
        sessions_ko,
        total_frames,
        total_bytes / 1024,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="Hôte de l'analyzer-gateway")
    parser.add_argument("--port", type=int, default=9000, help="Port du listener TCP brut")
    parser.add_argument(
        "--interval", type=float, default=2.0, help="Pause en secondes entre deux sessions"
    )
    parser.add_argument(
        "--protocol",
        choices=["hl7", "astm", "mixed"],
        default="mixed",
        help="Type de trames factices à générer",
    )
    parser.add_argument("--burst", type=int, default=1, help="Nombre de messages par session TCP")
    parser.add_argument(
        "--count", type=int, default=0, help="Nombre de sessions (0 = boucle infinie)"
    )
    parser.add_argument(
        "--abort-ratio",
        type=float,
        default=0.0,
        help="Proportion [0-1] de connexions coupées brutalement en pleine trame",
    )
    parser.add_argument(
        "--no-ack-wait", action="store_true", help="Ne pas attendre d'ACK après chaque trame"
    )
    parser.add_argument(
        "--ack-timeout", type=float, default=2.0, help="Délai max d'attente d'un ACK (s)"
    )
    parser.add_argument("--verbose", action="store_true", help="Logs DEBUG (ACK reçus…)")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_loop(args))
    except KeyboardInterrupt:
        logger.info("Interrompu par l'utilisateur.")


if __name__ == "__main__":
    main()
