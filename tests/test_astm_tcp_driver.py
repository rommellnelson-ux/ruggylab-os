"""Tests du driver autonome ASTM TCP/IP."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

_DRIVER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "astm_tcp_driver.py"
_SPEC = importlib.util.spec_from_file_location("astm_tcp_driver", _DRIVER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
astm_driver = importlib.util.module_from_spec(_SPEC)
sys.modules["astm_tcp_driver"] = astm_driver
_SPEC.loader.exec_module(astm_driver)


def test_parse_astm_order_and_result_records() -> None:
    raw = (
        b"\x05"
        b"\x021H|\\^&|||RUGGYLAB|||||P|1\r"
        b"O|1|SAMPLE-001||^^^NFS\r"
        b"R|1|^^^HGB^1|4.8|g/dL|L\r"
        b"R|2|^^^WBC^1|12.4|10^9/L|H\r"
        b"L|1|N\r\x033F\r\n"
        b"\x04"
    )

    batches = astm_driver.parse_astm_message(raw)

    assert len(batches) == 1
    batch = batches[0]
    assert batch.sample_barcode == "SAMPLE-001"
    assert batch.exam_code == "NFS"
    assert batch.data_points["HGB"] == {"value": 4.8, "unit": "g/dL"}
    assert batch.data_points["WBC"] == {"value": 12.4, "unit": "10^9/L"}


def test_parse_plain_astm_text_with_multiple_orders() -> None:
    raw = (
        "H|\\^&\r"
        "O|1|SAMPLE-A||^^^GLU\r"
        "R|1|^^^GLU|5,6|mmol/L\r"
        "O|2|SAMPLE-B||^^^CRP\r"
        "R|1|^^^CRP|18.2|mg/L\r"
        "L|1|N\r"
    )

    batches = astm_driver.parse_astm_message(raw)

    assert [batch.sample_barcode for batch in batches] == ["SAMPLE-A", "SAMPLE-B"]
    assert [batch.exam_code for batch in batches] == ["GLU", "CRP"]
    assert batches[0].data_points == {"GLU": {"value": 5.6, "unit": "mmol/L"}}
    assert batches[1].data_points == {"CRP": {"value": 18.2, "unit": "mg/L"}}


def test_sqlite_outbox_uses_wal_and_deduplicates(tmp_path: Path) -> None:
    outbox_path = tmp_path / "astm_outbox.sqlite3"
    outbox = astm_driver.SQLiteOutbox(outbox_path)
    payload = {
        "analyzer_id": "astm-test",
        "sample_barcode": "SAMPLE-OUTBOX",
        "data_points": {"HGB": 4.8},
    }

    asyncio.run(outbox.enqueue("same-key", payload))
    asyncio.run(outbox.enqueue("same-key", payload))

    with sqlite3.connect(outbox_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1


def test_outbox_keeps_failed_payload_for_retry(tmp_path: Path) -> None:
    outbox = astm_driver.SQLiteOutbox(tmp_path / "astm_outbox.sqlite3")
    client = astm_driver.RuggyLabRestClient(
        "http://127.0.0.1:9/api/v1",
        "driver-key",
        "astm-test",
    )
    driver = astm_driver.ASTMTCPDriver("127.0.0.1", 0, client, outbox)
    batch = astm_driver.ASTMOrderBatch(
        sample_barcode="SAMPLE-QUEUED",
        data_points={"HGB": 4.8},
        exam_code="NFS",
    )
    payload = client.payload_from_batch(batch)

    async def scenario() -> None:
        await outbox.enqueue("retry-key", payload)
        sent = await driver.dispatch_once()
        assert sent == 0
        assert await outbox.pending_count() == 1

    asyncio.run(scenario())

    with sqlite3.connect(outbox.path) as conn:
        row = conn.execute("SELECT status, attempts, payload_json FROM outbox").fetchone()
        assert row[0] == "failed"
        assert row[1] == 1
        assert json.loads(row[2])["sample_barcode"] == "SAMPLE-QUEUED"


def test_outbox_marks_payload_sent_after_success(tmp_path: Path) -> None:
    outbox = astm_driver.SQLiteOutbox(tmp_path / "astm_outbox.sqlite3")
    client = astm_driver.RuggyLabRestClient(
        "http://ruggylab.local/api/v1",
        "driver-key",
        "astm-test",
    )
    driver = astm_driver.ASTMTCPDriver("127.0.0.1", 0, client, outbox)
    payload = {
        "analyzer_id": "astm-test",
        "sample_barcode": "SAMPLE-SENT",
        "data_points": {"HGB": 4.8},
    }

    async def fake_post_payload(_payload):
        return {"status": "created", "result_id": 123}

    client.post_payload = fake_post_payload

    async def scenario() -> None:
        await outbox.enqueue("sent-key", payload)
        sent = await driver.dispatch_once()
        assert sent == 1
        assert await outbox.pending_count() == 0

    asyncio.run(scenario())

    with sqlite3.connect(outbox.path) as conn:
        row = conn.execute("SELECT status, sent_at FROM outbox").fetchone()
        assert row[0] == "sent"
        assert row[1] is not None
