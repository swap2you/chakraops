# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.3: Notifications Center — append-only store for UI parity with Slack events."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LAST_ORATS_WARN_AT: Optional[float] = None
_ORATS_WARN_THROTTLE_SEC = 3600  # 1 hour


def _notifications_path() -> Path:
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[2] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "notifications.jsonl"


def append_notification(
    severity: str,
    ntype: str,
    message: str,
    symbol: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append a notification to out/notifications.jsonl.
    severity: INFO | WARN | CRITICAL
    ntype: ORATS_WARN | SCHEDULER_MISSED | RECOMPUTE_FAILURE | REQUIRED_DATA_MISSING | etc.
    """
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp_utc": now,
        "severity": severity,
        "type": ntype,
        "symbol": symbol,
        "message": message,
        "details": details or {},
    }
    path = _notifications_path()
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    logger.info("[NOTIFICATIONS] Appended %s %s: %s", ntype, severity, message[:80])


def append_orats_warn(message: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Append ORATS WARN/DEGRADED notification (throttled to once per hour)."""
    global _LAST_ORATS_WARN_AT
    import time as _time
    now_ts = _time.time()
    with _LOCK:
        last = _LAST_ORATS_WARN_AT
        if last is not None and (now_ts - last) < _ORATS_WARN_THROTTLE_SEC:
            return
        _LAST_ORATS_WARN_AT = now_ts
    append_notification("WARN", "ORATS_WARN", message, symbol=None, details=details)


def load_notifications(limit: int = 100) -> List[Dict[str, Any]]:
    """Load last N notifications (newest first)."""
    path = _notifications_path()
    if not path.exists():
        return []
    lines: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                lines.append(s)
    out: List[Dict[str, Any]] = []
    for s in reversed(lines[-limit:]):
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out
