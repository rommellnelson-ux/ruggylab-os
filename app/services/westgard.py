"""Westgard multi-rule QC evaluation engine.

Rules evaluated (in order of severity):
  1-2s  warning — 1 point outside mean ± 2SD
  1-3s  reject  — 1 point outside mean ± 3SD
  2-2s  reject  — 2 consecutive points outside ± 2SD (same side)
  R-4s  reject  — range of 2 consecutive points > 4SD
  4-1s  reject  — 4 consecutive points outside ± 1SD (same side)
  10x   reject  — 10 consecutive points on same side of mean

Reference: Westgard JO. Basic QC Practices, 3rd ed. (2008)
"""

from __future__ import annotations


def check_westgard(values: list[float], mean: float, sd: float) -> list[str]:
    """Return list of violated Westgard rule codes for the *latest* value.

    Args:
        values: chronological list of measurements (most recent = last).
        mean:   target mean of the control material.
        sd:     target standard deviation (must be > 0).

    Returns:
        Sorted list of rule codes, e.g. ["1-2s", "2-2s"].
        Empty list means no rule violated (in-control).
    """
    if not values or sd <= 0:
        return []

    z = [(v - mean) / sd for v in values]
    latest = z[-1]
    violations: list[str] = []

    # ── Single-value rules ───────────────────────────────────────────────────
    if abs(latest) > 3:
        violations.append("1-3s")  # reject
    elif abs(latest) > 2:
        violations.append("1-2s")  # warning only (not reject by itself)

    # ── Two-point rules ──────────────────────────────────────────────────────
    if len(z) >= 2:
        prev = z[-2]
        # R-4s: two consecutive points span more than 4 SD
        if abs(latest - prev) > 4:
            violations.append("R-4s")
        # 2-2s: two consecutive points both beyond ±2SD on the same side
        if latest > 2 and prev > 2 or latest < -2 and prev < -2:
            violations.append("2-2s")

    # ── Four-point rule ──────────────────────────────────────────────────────
    if len(z) >= 4:
        last4 = z[-4:]
        if all(v > 1 for v in last4) or all(v < -1 for v in last4):
            violations.append("4-1s")

    # ── Ten-point rule ───────────────────────────────────────────────────────
    if len(z) >= 10:
        last10 = z[-10:]
        if all(v > 0 for v in last10) or all(v < 0 for v in last10):
            violations.append("10x")

    return violations
