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
    R28.3: Persist only safe severity + severity_label (no raw WARN/FAIL/PASS in file).
    severity: INFO | WARN | CRITICAL (caller may pass raw; we normalize before persist).
    R70-DEF-050: suppress byte-identical active (NEW/ACKED) duplicates.
    """
    from app.core.notifications.notification_safe_labels import normalize_notification_severity
    safe_severity, severity_label = normalize_notification_severity(severity or "INFO")
    msg = message or ""
    sym = symbol
    # Durable dedupe: identical type+message+symbol+subtype already active → no-op
    try:
        existing = load_notifications(limit=200, state_filter=None, type_filter=ntype)
        for rec in existing:
            st = rec.get("state") or "NEW"
            if st not in ("NEW", "ACKED"):
                continue
            if (rec.get("message") or "") != msg:
                continue
            if (rec.get("symbol") or None) != (sym or None):
                continue
            if (rec.get("subtype") or None) != (subtype or None):
                continue
            logger.info("[NOTIFICATIONS] Dedupe skip %s: %s", ntype, msg[:80])
            return
    except Exception as exc:
        logger.warning("[NOTIFICATIONS] dedupe check failed: %s", type(exc).__name__)
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "timestamp_utc": now,
        "severity": safe_severity,
        "severity_label": severity_label,
        "type": ntype,
        "subtype": subtype,
        "symbol": symbol,
        "message": msg,
        "details": details or {},
    }
    path = _notifications_path()
    line = json.dumps(record, default=str)
    with _LOCK:
        from app.core.io.locks import with_file_lock
        with with_file_lock(path, timeout_ms=2000):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _prune_if_needed(path)
    logger.info("[NOTIFICATIONS] Appended %s %s: %s", ntype, safe_severity, msg[:80])


def _append_state_event(ref_id: str, state: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """Append a state event (append-only). state: ACKED | ARCHIVED | DELETED."""
    now = datetime.now(timezone.utc).isoformat()
    record: Dict[str, Any] = {"event": "state", "ref_id": ref_id, "state": state, "updated_at": now, **(extra or {})}
    path = _notifications_path()
    line = json.dumps(record, default=str)
    with _LOCK:
        from app.core.io.locks import with_file_lock
        with with_file_lock(path, timeout_ms=2000):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _prune_if_needed(path)
    logger.info("[NOTIFICATIONS] State %s for %s", state, ref_id[:20])


def append_archive(ref_id: str) -> None:
    """Phase 21.5: Archive a notification (append state event)."""
    _append_state_event(ref_id, "ARCHIVED")


def append_delete(ref_id: str) -> None:
    """Phase 21.5: Delete (soft) a notification (append state event). Excluded from list."""
    _append_state_event(ref_id, "DELETED")


def archive_all(limit: int = 5000) -> int:
    """
    Phase 21.5: Append ARCHIVED state event for every notification that is NEW or ACKED.
    Returns count of notifications archived. Optional limit caps how many we consider.
    """
    all_recs = load_notifications(limit=limit, state_filter=None)
    count = 0
    for rec in all_recs:
        st = rec.get("state", "NEW")
        if st in ("NEW", "ACKED"):
            append_archive(rec["id"])
            count += 1
    return count


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
        from app.core.io.locks import with_file_lock
        with with_file_lock(path, timeout_ms=2000):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _prune_if_needed(path)
    logger.info("[NOTIFICATIONS] Ack %s by %s", ref_id[:20], ack_by)


def _orats_warn_throttle_path() -> Path:
    return _notifications_path().parent / "orats_warn_throttle.json"


def _load_orats_warn_throttle() -> Optional[float]:
    global _LAST_ORATS_WARN_AT
    if _LAST_ORATS_WARN_AT is not None:
        return _LAST_ORATS_WARN_AT
    path = _orats_warn_throttle_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = float(data.get("last_warn_at") or 0)
        _LAST_ORATS_WARN_AT = ts if ts > 0 else None
        return _LAST_ORATS_WARN_AT
    except Exception:
        return None


def _save_orats_warn_throttle(ts: float) -> None:
    global _LAST_ORATS_WARN_AT
    _LAST_ORATS_WARN_AT = ts
    path = _orats_warn_throttle_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"last_warn_at": ts}), encoding="utf-8")
    except OSError:
        logger.warning("[NOTIFICATIONS] failed to persist ORATS warn throttle")


def append_orats_warn(message: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Append ORATS WARN/DEGRADED notification (throttled to once per hour; durable across restarts)."""
    import time as _time
    now_ts = _time.time()
    with _LOCK:
        last = _load_orats_warn_throttle()
        if last is not None and (now_ts - last) < _ORATS_WARN_THROTTLE_SEC:
            return
        _save_orats_warn_throttle(now_ts)
    # Append outside throttle lock to avoid nested lock with append_notification
    append_notification("WARN", "ORATS_WARN", message, symbol=None, details=details, subtype="ORATS_STALE")


def load_notifications(
    limit: int = 100,
    state_filter: Optional[str] = None,
    symbol_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Load notifications (newest first). R25.4: symbol_filter, type_filter, offset.
    Phase 10.3: Parses ack events, merges ack_at_utc/ack_by.
    Phase 21.5: state and updated_at from state events.
    R25.4: Adds created_ts, acked_ts, archived_ts for API parity.
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

    notifications = []
    acks: Dict[str, tuple[str, str]] = {}
    state_events: Dict[str, tuple[str, str]] = {}

    for s in lines:
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        ev = obj.get("event")
        if ev == "ack":
            ref_id = obj.get("ref_id")
            ack_at = obj.get("ack_at_utc")
            ack_by_val = obj.get("ack_by", "ui")
            if ref_id and ack_at:
                acks[ref_id] = (ack_at, ack_by_val)
        elif ev == "state":
            ref_id = obj.get("ref_id")
            st = obj.get("state")
            updated = obj.get("updated_at")
            if ref_id and st and updated:
                state_events[ref_id] = (st, updated)
        else:
            notifications.append(obj)

    sym_q = (symbol_filter or "").strip().upper()
    type_q = (type_filter or "").strip() if type_filter else ""
    seen_ids: Set[str] = set()
    out: List[Dict[str, Any]] = []
    skipped = 0
    for rec in reversed(notifications[-limit * 5:]):
        nid = rec.get("id") or _stable_id_for_record(rec)
        rec["id"] = nid
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        ack_data = acks.get(nid)
        if ack_data:
            rec["ack_at_utc"] = ack_data[0]
            rec["ack_by"] = ack_data[1]
        state = "NEW"
        updated_at = rec.get("timestamp_utc")
        if nid in state_events:
            st, uat = state_events[nid]
            state = st
            updated_at = uat
        elif ack_data:
            state = "ACKED"
            updated_at = ack_data[0]
        rec["state"] = state
        rec["updated_at"] = updated_at
        if state == "DELETED" and state_filter != "DELETED":
            continue
        if state_filter and state != state_filter:
            continue
        if sym_q and (rec.get("symbol") or "").strip().upper() != sym_q:
            continue
        if type_q and (rec.get("type") or "").strip() != type_q:
            continue
        rec["created_ts"] = rec.get("timestamp_utc")
        rec["acked_ts"] = rec.get("ack_at_utc") if ack_data else None
        rec["archived_ts"] = updated_at if state == "ARCHIVED" else None
        # R28.3: Normalize for API — safe severity/severity_label only; sanitize message (no FAIL/WARN/PASS)
        _normalize_rec_for_api(rec)
        if offset and skipped < offset:
            skipped += 1
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def _normalize_rec_for_api(rec: Dict[str, Any]) -> None:
    """R28.3: Ensure rec has safe severity/severity_label; sanitize message. Mutates rec in place."""
    from app.core.notifications.notification_safe_labels import (
        normalize_notification_severity,
        sanitize_message_for_api,
    )
    raw_sev = rec.get("severity") or ""
    if (raw_sev or "").strip().upper() in ("FAIL", "WARN", "PASS", "INFO", "CRITICAL", "ERROR"):
        safe_sev, safe_label = normalize_notification_severity(raw_sev)
        rec["severity"] = safe_sev
        rec["severity_label"] = safe_label
    elif not rec.get("severity_label"):
        safe_sev, safe_label = normalize_notification_severity(raw_sev or "INFO")
        rec["severity"] = rec.get("severity") or safe_sev
        rec["severity_label"] = safe_label
    msg = rec.get("message")
    if msg is not None and isinstance(msg, str):
        rec["message"] = sanitize_message_for_api(msg)


def get_notifications_health() -> Dict[str, Any]:
    """
    R25.4: Counts by state and last emitted ts for System Health. Safe labels only.
    """
    all_recs = load_notifications(limit=5000, state_filter=None)
    count_new = sum(1 for r in all_recs if r.get("state") == "NEW")
    count_acked = sum(1 for r in all_recs if r.get("state") == "ACKED")
    count_archived = sum(1 for r in all_recs if r.get("state") == "ARCHIVED")
    last_ts: Optional[str] = None
    for r in all_recs:
        ts = r.get("timestamp_utc") or r.get("created_ts")
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts
    return {
        "count_new": count_new,
        "count_acked": count_acked,
        "count_archived": count_archived,
        "last_emitted_ts": last_ts,
    }


def ack_bulk(state_filter: Optional[str] = "NEW") -> int:
    """
    R25.4: Append ack for each notification in state NEW (or optional filter). Returns count acked.
    """
    recs = load_notifications(limit=500, state_filter=state_filter or "NEW")
    count = 0
    for rec in recs:
        nid = rec.get("id")
        if nid and rec.get("state") == "NEW":
            append_ack(ref_id=nid, ack_by="ui")
            count += 1
    return count


def archive_bulk(state_filter: Optional[str] = "ACKED") -> int:
    """
    R25.4: Append archive for each notification in state ACKED (or optional filter). Returns count archived.
    """
    recs = load_notifications(limit=500, state_filter=state_filter or "ACKED")
    count = 0
    for rec in recs:
        nid = rec.get("id")
        if nid and rec.get("state") == "ACKED":
            append_archive(nid)
            count += 1
    return count


def maybe_append_shares_exit_notification(
    symbol: str,
    hit_type: str,
    last_price: float,
    target_price: Optional[float],
    stop_price: Optional[float],
    as_of_ts: Optional[str],
) -> bool:
    """
    R25.2/R25.4: Append SHARES_EXIT_SIGNAL only if no active (NEW/ACKED) for same symbol+hit_type.
    Transition-aware dedupe: one per (symbol, hit_type) until acked/archived; then re-trigger allowed.
    Returns True if appended, False if deduped. Safe labels only.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or hit_type not in ("TARGET", "STOP"):
        return False
    recent = load_notifications(limit=500, state_filter=None)
    for rec in recent:
        if rec.get("type") != "SHARES_EXIT_SIGNAL":
            continue
        if (rec.get("symbol") or "").strip().upper() != symbol:
            continue
        details = rec.get("details") or {}
        if details.get("hit_type") != hit_type:
            continue
        if rec.get("state") in ("NEW", "ACKED"):
            return False
    title = "Target hit" if hit_type == "TARGET" else "Stop hit"
    message = f"Shares exit: {symbol} — {title}. Consider closing position."
    details = {
        "hit_type": hit_type,
        "last_price": last_price,
        "target_price": target_price,
        "stop_price": stop_price,
        "as_of_ts": as_of_ts,
    }
    append_notification("INFO", "SHARES_EXIT_SIGNAL", message, symbol=symbol, details=details, subtype=hit_type)
    return True


# R25.3: Options lifecycle notification types
OPTIONS_PROFIT_TARGET_HIT = "OPTIONS_PROFIT_TARGET_HIT"
OPTIONS_ROLL_WINDOW = "OPTIONS_ROLL_WINDOW"
OPTIONS_ASSIGNMENT_RISK = "OPTIONS_ASSIGNMENT_RISK"


def maybe_append_options_lifecycle_notification(
    symbol: str,
    contract_key: str,
    event_type: str,
    payload: Dict[str, Any],
) -> bool:
    """
    R25.3/R25.4: Append options lifecycle notification only if no active (NEW/ACKED) for same
    contract_key+event_type. Transition-aware dedupe: one per (contract_key, event_type) until
    acked/archived; then re-trigger allowed. Safe labels only.
    """
    symbol = (symbol or "").strip().upper()
    contract_key = (contract_key or "").strip()
    if not symbol or not contract_key or event_type not in (
        OPTIONS_PROFIT_TARGET_HIT,
        OPTIONS_ROLL_WINDOW,
        OPTIONS_ASSIGNMENT_RISK,
    ):
        return False
    recent = load_notifications(limit=500, state_filter=None)
    for rec in recent:
        if rec.get("type") != event_type:
            continue
        if (rec.get("symbol") or "").strip().upper() != symbol:
            continue
        details = rec.get("details") or {}
        if (details.get("contract_key") or "").strip() != contract_key:
            continue
        if rec.get("state") in ("NEW", "ACKED"):
            return False
    # Safe labels only
    if event_type == OPTIONS_PROFIT_TARGET_HIT:
        message = f"Options: {symbol} — Profit target hit. Consider closing."
    elif event_type == OPTIONS_ROLL_WINDOW:
        message = f"Options: {symbol} — Roll window. Consider rolling."
    else:
        message = f"Options: {symbol} — Assignment risk. Consider closing or rolling."
    details = {k: v for k, v in (payload or {}).items() if k in (
        "symbol", "contract_key", "expiry", "strike", "right", "dte",
        "profit_pct", "mark_value", "as_of_ts", "recommended_action_code",
    )}
    details["contract_key"] = contract_key
    if symbol and "symbol" not in details:
        details["symbol"] = symbol
    append_notification("INFO", event_type, message, symbol=symbol, details=details, subtype=event_type)
    return True


# R26.4: Ops checklist reminder types (safe; no FAIL/WARN)
OPS_EOD_CHECKLIST_REMINDER = "OPS_EOD_CHECKLIST_REMINDER"
OPS_WEEKLY_REVIEW_REMINDER = "OPS_WEEKLY_REVIEW_REMINDER"


# R27.7: CC eligibility advisory (safe labels only; dedupe by symbol while NEW/ACKED)
CC_ELIGIBLE = "CC_ELIGIBLE"


def maybe_append_cc_eligible_notification(symbol: str) -> bool:
    """
    R27.7: Append CC_ELIGIBLE advisory only if no active (NEW/ACKED) for same symbol.
    Dedupe: one per symbol until acked/archived; then re-trigger allowed. Safe labels only.
    Returns True if appended, False if deduped.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return False
    recent = load_notifications(limit=500, state_filter=None)
    for rec in recent:
        if rec.get("type") != CC_ELIGIBLE:
            continue
        if (rec.get("symbol") or "").strip().upper() != symbol:
            continue
        if rec.get("state") in ("NEW", "ACKED"):
            return False
    message = f"Shares eligible for covered call: {symbol}. Consider opening CC ticket."
    append_notification("INFO", CC_ELIGIBLE, message, symbol=symbol, details={"symbol": symbol}, subtype=CC_ELIGIBLE)
    return True


def maybe_append_ops_checklist_reminder(reminder_type: str, key: str) -> bool:
    """
    R26.4: Append EOD or Weekly reminder only if no active (NEW/ACKED) for same type+key.
    Dedupe: one per key until acked/archived. Safe labels only.
    """
    if reminder_type not in (OPS_EOD_CHECKLIST_REMINDER, OPS_WEEKLY_REVIEW_REMINDER):
        return False
    key = (key or "").strip()
    if not key:
        return False
    recent = load_notifications(limit=500, state_filter=None)
    for rec in recent:
        if rec.get("type") != reminder_type:
            continue
        if (rec.get("details") or {}).get("key") != key:
            continue
        if rec.get("state") in ("NEW", "ACKED"):
            return False
    if reminder_type == OPS_EOD_CHECKLIST_REMINDER:
        message = f"EOD checklist pending for {key}. Complete before tomorrow."
    else:
        message = f"Weekly review pending for week {key}. Complete when ready."
    append_notification(
        "INFO",
        reminder_type,
        message,
        symbol=None,
        details={"key": key},
        subtype=reminder_type,
    )
    return True
