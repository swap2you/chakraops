# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.3: Notifications Center — append-only store for UI parity with Slack events.
   Phase 10.3: Append-only ack events (ack_at_utc, ack_by)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# Phase 8.6: Retention — keep last N lines
_RETENTION_LINES = 5000
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


def _prune_if_needed(path: Path) -> None:
    """If file exceeds _RETENTION_LINES, rewrite with last N lines (atomic)."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) <= _RETENTION_LINES:
        return
    kept = lines[-_RETENTION_LINES:]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="notifications.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ln in kept:
                f.write(ln + "\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def _stable_id_for_record(record: Dict[str, Any]) -> str:
    """Derive stable id for a record missing id (backwards compat)."""
    parts = [
        str(record.get("timestamp_utc", "")),
        str(record.get("type", "")),
        str(record.get("message", "")),
        str(record.get("symbol", "")),
    ]
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"n_{h[:16]}"


def append_notification(
    severity: str,
    ntype: str,
    message: str,
    symbol: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    subtype: Optional[str] = None,
) -> None:
    """
    Append a notification to out/notifications.jsonl.
    severity: INFO | WARN | CRITICAL
    ntype: ORATS_WARN | SCHEDULER_MISSED | RECOMPUTE_FAILURE | REQUIRED_DATA_MISSING | etc.
    subtype: Optional (e.g. RUN_ERRORS, LOW_COMPLETENESS, ORATS_STALE, SCHEDULER_MISSED).
    Phase 10.3: Each record gets an id for ack targeting.
    """
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "timestamp_utc": now,
        "severity": severity,
        "type": ntype,
        "subtype": subtype,
        "symbol": symbol,
        "message": message,
        "details": details or {},
    }
    path = _notifications_path()
    line = json.dumps(record, default=str)
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _prune_if_needed(path)
    logger.info("[NOTIFICATIONS] Appended %s %s: %s", ntype, severity, message[:80])


def append_ack(ref_id: str, ack_by: str = "ui") -> None:
    """
    Append an ack event (append-only). Merged into notifications by load_notifications.
    Phase 10.3.
    """
    now = datetime.now(timezone.utc).isoformat()
    record = {"event": "ack", "ref_id": ref_id, "ack_at_utc": now, "ack_by": ack_by}
    path = _notifications_path()
    line = json.dumps(record, default=str)
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _prune_if_needed(path)
    logger.info("[NOTIFICATIONS] Ack %s by %s", ref_id[:20], ack_by)


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
    append_notification("WARN", "ORATS_WARN", message, symbol=None, details=details, subtype="ORATS_STALE")


def load_notifications(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Load last N notifications (newest first).
    Phase 10.3: Parses ack events, merges ack_at_utc/ack_by into notifications.
    Records without id get a derived stable id for backwards compat.
    """
    path = _notifications_path()
    if not path.exists():
        return []
    lines: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                lines.append(s)

    # Collect notifications and ack events
    notifications: List[Dict[str, Any]] = []
    acks: Dict[str, tuple[str, str]] = {}  # ref_id -> (ack_at_utc, ack_by)

    for s in lines:
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if obj.get("event") == "ack":
            ref_id = obj.get("ref_id")
            ack_at = obj.get("ack_at_utc")
            ack_by_val = obj.get("ack_by", "ui")
            if ref_id and ack_at:
                acks[ref_id] = (ack_at, ack_by_val)
        else:
            notifications.append(obj)

    # Ensure ids, merge acks, newest first
    seen_ids: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for rec in reversed(notifications[-limit:]):
        nid = rec.get("id")
        if not nid:
            nid = _stable_id_for_record(rec)
            rec["id"] = nid
        # Dedupe by id (same logical notification may appear if file has duplicates)
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        ack_data = acks.get(nid)
        if ack_data:
            rec["ack_at_utc"] = ack_data[0]
            rec["ack_by"] = ack_data[1]
        out.append(rec)
    return out
