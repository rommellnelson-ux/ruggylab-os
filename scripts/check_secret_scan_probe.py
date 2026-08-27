"""Prove that detect-secrets rejects a newly generated synthetic credential."""

from __future__ import annotations

import secrets
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        probe = Path(directory) / "secret_scan_probe.py"
        probe.write_text(
            "service_password = " + repr(secrets.token_urlsafe(48)) + "\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            ["detect-secrets-hook", str(probe)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    if completed.returncode == 0:
        print("Negative secret-scan probe was not detected.")
        return 1
    print("Negative secret-scan probe was detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
