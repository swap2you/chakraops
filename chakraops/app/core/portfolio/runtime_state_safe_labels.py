# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.2: Normalize raw PASS/FAIL/WARN to safe status + label for UI-facing runtime state files in out/."""

from __future__ import annotations

from typing import Tuple

# Safe status set for persisted runtime state (no raw FAIL/WARN/PASS in files).
SAFE_STATUSES = ("OK", "Review", "Blocked", "Degraded")


def normalize_runtime_status(raw: str) -> Tuple[str, str]:
    """
    Map raw status to (safe_status, safe_label) for persistence and UI.
    Raw PASS/FAIL/WARN must not appear in out/ runtime state files.
    R28.3: FAIL (limit breach) -> Degraded; Blocked reserved for truly blocked/stop conditions.
    """
    r = (raw or "").strip().upper()
    if r == "PASS":
        return ("OK", "OK")
    if r == "FAIL":
        return ("Degraded", "Limit breach")
    if r == "WARN":
        return ("Degraded", "Advisory")
    return ("OK", "OK")


def normalize_mark_refresh_result(raw: str) -> Tuple[str, str]:
    """Mark-refresh specific labels: PASS->OK, WARN->Degraded/Partial update, FAIL->Blocked/No update."""
    r = (raw or "").strip().upper()
    if r == "PASS":
        return ("OK", "OK")
    if r == "WARN":
        return ("Degraded", "Partial update")
    if r == "FAIL":
        return ("Blocked", "No update")
    return ("OK", "OK")
