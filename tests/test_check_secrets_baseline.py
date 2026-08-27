from __future__ import annotations

import json
from pathlib import Path

from scripts.check_secrets_baseline import compare_baseline_documents, validate_baseline


def _write_baseline(path: Path, results: dict[str, list[object]], version: str = "1.5.0") -> None:
    path.write_text(json.dumps({"version": version, "results": results}), encoding="utf-8")


def test_accepts_existing_posix_paths(tmp_path: Path) -> None:
    tracked = tmp_path / "docs" / "example.md"
    tracked.parent.mkdir()
    tracked.write_text("placeholder", encoding="utf-8")
    baseline = tmp_path / ".secrets.baseline"
    _write_baseline(baseline, {"docs/example.md": []})

    assert validate_baseline(baseline, tmp_path) == []


def test_rejects_windows_absolute_missing_and_wrong_version(tmp_path: Path) -> None:
    tracked = tmp_path / "docs" / "example.md"
    tracked.parent.mkdir()
    tracked.write_text("placeholder", encoding="utf-8")
    baseline = tmp_path / ".secrets.baseline"
    _write_baseline(
        baseline,
        {
            "docs\\example.md": [],
            "docs/example.md": [],
            "C:\\outside.txt": [],
            "missing.txt": [],
        },
        version="0.0.0",
    )

    errors = validate_baseline(baseline, tmp_path)

    assert any("expected version 1.5.0" in error for error in errors)
    assert any("Windows path separator" in error for error in errors)
    assert any("absolute path" in error for error in errors)
    assert any("duplicates" in error for error in errors)
    assert any("missing.txt: tracked file does not exist" in error for error in errors)


def test_rejects_non_posix_nested_filename(tmp_path: Path) -> None:
    tracked = tmp_path / "docs" / "example.md"
    tracked.parent.mkdir()
    tracked.write_text("placeholder", encoding="utf-8")
    baseline = tmp_path / ".secrets.baseline"
    _write_baseline(
        baseline,
        {"docs/example.md": [{"filename": "docs\\example.md"}]},
    )

    assert validate_baseline(baseline, tmp_path) == [
        "docs/example.md: nested filename must match its POSIX result path"
    ]


def test_rejects_invalid_json_without_leaking_content(tmp_path: Path) -> None:
    baseline = tmp_path / ".secrets.baseline"
    baseline.write_text("not-json", encoding="utf-8")

    errors = validate_baseline(baseline, tmp_path)

    assert errors == [".secrets.baseline: invalid baseline (JSONDecodeError)"]


def test_stability_ignores_only_generated_at() -> None:
    before = {
        "version": "1.5.0",
        "generated_at": "first",
        "results": {"tests/example.py": [{"type": "Secret Keyword", "hashed_secret": "one"}]},
    }
    after = {
        **before,
        "generated_at": "second",
    }

    assert compare_baseline_documents(before, after) == []

    after["results"] = {
        "tests/example.py": [{"type": "Secret Keyword", "hashed_secret": "different"}]
    }
    assert compare_baseline_documents(before, after) == [
        "tests/example.py: baseline results changed during update"
    ]
