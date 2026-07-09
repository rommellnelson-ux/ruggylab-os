"""Le process scheduler écrit un battement récent (base du healthcheck compose)."""

import asyncio
import time

import app.scheduler as scheduler


def test_heartbeat_loop_writes_fresh_timestamp(tmp_path) -> None:  # noqa: ANN001
    hb = tmp_path / "hb"

    async def _run() -> None:
        task = asyncio.create_task(scheduler._heartbeat_loop(str(hb), interval_seconds=60))
        # Laisse un tour d'écriture s'exécuter, puis arrête proprement.
        for _ in range(50):
            if hb.exists():
                break
            await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())

    assert hb.exists(), "le heartbeat n'a pas été écrit"
    written = int(hb.read_text())
    assert abs(time.time() - written) < 5
