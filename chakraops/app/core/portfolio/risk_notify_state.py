# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 16.0: Portfolio risk notification state — throttled emission of identical breaches."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_THROTTLE_SEC = 3600  # 60 minutes


def _risk_notify_state_path() -> Path:
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "portfolio_risk_notify_state.json"


def _breach_signature(breaches: List[Dict[str, Any]]) -> str:
    """Signature hash: sorted breaches type/subtype/symbol/current/limit."""
    parts: List[str] = []
    aff = lambda b: ",".join(sorted(b.get("affected_symbols") or []))
    for b in sorted(breaches, key=lambda x: (str(x.get("type")), str(x.get("subtype", "")), aff(x), str(x.get("current")), str(x.get("limit")))):
        t = str(b.get("type", ""))
        st = str(b.get("subtype", b.get("code", "")))
        sym = aff(b)
        cur = str(b.get("current", b.get("value", b.get("utilization_pct", ""))))
        lim = str(b.get("limit", b.get("max_pct", b.get("max_util", ""))))
        parts.append(f"{t}|{st}|{sym}|{cur}|{lim}")
    h = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return h[:32]


def _load_state() -> Dict[str, Any]:
    path = _risk_notify_state_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug("Failed to load portfolio_risk_notify_state: %s", e)
        return {}


def _save_state(last_signature: str, last_notified_at_utc: str, last_status: str) -> None:
    path = _risk_notify_state_path()
    try:
        from app.core.io.atomic import atomic_write_json
        data = {
            "last_signature": last_signature,
            "last_notified_at_utc": last_notified_at_utc,
            "last_status": last_status,
        }
        atomic_write_json(path, data, indent=0)
    except Exception as e:
        logger.warning("[RISK_NOTIFY] Failed to write state: %s", e)


def should_emit_portfolio_risk_notification(
    status: str,
    breaches: List[Dict[str, Any]],
) -> bool:
    """
    Return True if we should emit a notification.
    Emit only if: signature changed OR >60 min since last emit OR status transition (e.g. PASS->FAIL).
    """
    if status not in ("FAIL", "WARN") or not breaches:
        return False
    sig = _breach_signature(breaches)
    state = _load_state()
    prev_sig = state.get("last_signature", "")
    prev_status = state.get("last_status", "")
    prev_ts_str = state.get("last_notified_at_utc", "")
    now_ts = time.time()
    now_utc = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    # Signature changed: always emit
    if sig != prev_sig:
        _save_state(sig, now_utc, status)
        return True

    # Status transition (e.g. was PASS, now FAIL)
    if prev_status != status:
        _save_state(sig, now_utc, status)
        return True

    # Same signature: only if >60 min since last
    if not prev_ts_str:
        _save_state(sig, now_utc, status)
        return True
    try:
        prev_dt = __import__("datetime").datetime.fromisoformat(prev_ts_str.replace("Z", "+00:00"))
        prev_ts = prev_dt.timestamp()
        if (now_ts - prev_ts) >= _THROTTLE_SEC:
            _save_state(sig, now_utc, status)
            return True
    except (ValueError, TypeError, OSError):
        _save_state(sig, now_utc, status)
        return True

    return False
