from __future__ import annotations

import logging

import pytest

from scripts import process_report_delivery_outbox as worker


@pytest.mark.parametrize(
    ("converter", "value"),
    [
        (worker.positive_int, "0"),
        (worker.positive_int, "-1"),
        (worker.positive_float, "0"),
        (worker.positive_float, "-0.1"),
    ],
)
def test_worker_rejects_non_positive_values(converter, value: str) -> None:
    with pytest.raises(Exception, match="strictement positive"):
        converter(value)


def test_worker_check_does_not_process_outbox(monkeypatch) -> None:
    checked = []
    monkeypatch.setattr(worker, "_check_database", lambda: checked.append(True))
    monkeypatch.setattr(
        worker,
        "_run_once",
        lambda **_kwargs: pytest.fail("Le check ne doit pas consommer la file"),
    )

    assert worker.main(["--check"]) == 0
    assert checked == [True]


def test_worker_once_processes_one_batch(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(worker, "_run_once", lambda **kwargs: calls.append(kwargs))

    assert worker.main(["--once", "--limit", "12", "--max-attempts", "3"]) == 0
    assert calls == [{"limit": 12, "max_attempts": 3}]


def test_worker_can_write_log_file(tmp_path) -> None:
    log_file = tmp_path / "nested" / "worker.log"

    worker._configure_logging(log_file)
    worker.logger.info("worker-test-marker")
    logging.shutdown()

    assert "worker-test-marker" in log_file.read_text(encoding="utf-8")
