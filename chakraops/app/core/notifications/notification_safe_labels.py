# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.3: Normalize notification severity/status to safe labels for persistence and UI. No FAIL/WARN/PASS in output."""

from __future__ import annotations

import re
from typing import Tuple

# Forbidden in UI-facing notification data
_FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)


def normalize_notification_severity(raw: str) -> Tuple[str, str]:
    """
    Map raw severity to (safe_severity, safe_label) for persistence and API.
    Raw INFO/WARN/CRITICAL/ERROR/FAIL/PASS must not appear in out/notifications.jsonl or API response.
    """
    r = (raw or "").strip().upper()
    if r in ("INFO", "PASS"):
        return ("Low", "Info" if r == "INFO" else "OK")
    if r == "WARN":
        return ("Medium", "Advisory")
    if r in ("CRITICAL", "ERROR", "FAIL"):
        return ("High", "Review")
    return ("Medium", "Review")  # conservative unknown


def normalize_notification_status(raw: str) -> Tuple[str, str]:
    """Map raw status to (safe_status, safe_label). For optional status field on notifications."""
    r = (raw or "").strip().upper()
    if r == "PASS":
        return ("OK", "OK")
    if r == "FAIL":
        return ("Blocked", "Review")
    if r == "WARN":
        return ("Review", "Advisory")
    return ("Review", "Review")  # conservative unknown


def sanitize_message_for_api(msg: str | None) -> str:
    """Replace raw FAIL/WARN/PASS in message so API never returns those tokens. R28.3."""
    if msg is None or not isinstance(msg, str):
        return "" if msg is None else str(msg)
    return _FORBIDDEN.sub(
        lambda m: {"FAIL": "Review", "WARN": "Advisory", "PASS": "OK"}.get(m.group(1).upper(), "Review"),
        msg,
    )


_JOB_LABELS = {
    "weekly_universe_refresh": "Weekly universe refresh",
    "eod_data_refresh": "EOD data refresh",
    "decision_generation": "Decision generation",
    "nightly_reports": "Nightly reports",
    "backup": "Backup",
    "provider_health": "Provider health",
    "retention_cleanup": "Retention cleanup",
    "recovery_reconciliation": "Recovery reconciliation",
}


def to_safe_operator_label(job_id: str) -> str:
    """Map internal job id to operator-friendly label (no raw codes)."""
    return _JOB_LABELS.get(job_id, job_id.replace("_", " ").title())
