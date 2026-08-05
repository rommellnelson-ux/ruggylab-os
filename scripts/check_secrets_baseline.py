"""Validate the portable, non-sensitive structure of .secrets.baseline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

EXPECTED_VERSION = "1.5.0"
JUSTIFIED_MISSING_PATHS: frozenset[str] = frozenset()


def validate_baseline(baseline_path: Path, repository_root: Path) -> list[str]:
    """Return redacted structural errors without reading or printing candidates."""
    try:
        document: dict[str, Any] = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{baseline_path.name}: invalid baseline ({type(exc).__name__})"]

    errors: list[str] = []
    if document.get("version") != EXPECTED_VERSION:
        errors.append(f"{baseline_path.name}: expected version {EXPECTED_VERSION}")

    results = document.get("results")
    if not isinstance(results, dict):
        return [*errors, f"{baseline_path.name}: results must be an object"]

    canonical_sources: dict[str, str] = {}
    for raw_path in results:
        if not isinstance(raw_path, str):
            errors.append(f"{baseline_path.name}: non-string result path")
            continue

        if "\\" in raw_path:
            errors.append(f"{raw_path}: Windows path separator is forbidden")

        canonical = raw_path.replace("\\", "/")
        if (
            PurePosixPath(canonical).is_absolute()
            or PureWindowsPath(raw_path).is_absolute()
            or os.path.isabs(raw_path)
        ):
            errors.append(f"{raw_path}: absolute path is forbidden")

        previous = canonical_sources.setdefault(canonical, raw_path)
        if previous != raw_path:
            errors.append(f"{raw_path}: duplicates {previous} after canonicalization")

        parts = PurePosixPath(canonical).parts
        if not canonical or any(part in {"", ".", ".."} for part in parts):
            errors.append(f"{raw_path}: path is not a canonical repository-relative path")
            continue

        if canonical not in JUSTIFIED_MISSING_PATHS and not (repository_root / canonical).is_file():
            errors.append(f"{raw_path}: tracked file does not exist")

    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", nargs="?", type=Path, default=Path(".secrets.baseline"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    errors = validate_baseline(args.baseline, args.root.resolve())
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Secret baseline structure is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
