# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 16.0: Mark refresh state — operational state file for last run, exposed in system health."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MARK_REFRESH_THROTTLE_SEC = 3600  # 1 hour
_LAST_MARK_REFRESH_FAIL_NOTIFIED_AT: Optional[float] = None


def _mark_refresh_state_path() -> Path:
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "mark_refresh_state.json"


def write_mark_refresh_state(
    updated_count: int,
    skipped_count: int,
    errors: List[str],
) -> None:
    """
    Write out/mark_refresh_state.json after marks refresh run.
    last_result: PASS if errors=0; WARN if errors>0 but updated_count>0; FAIL if updated_count==0 and errors>0.
    """
    now = datetime.now(timezone.utc).isoformat()
    error_count = len(errors)
    if error_count == 0:
        last_result = "PASS"
    elif updated_count > 0:
        last_result = "WARN"
    else:
        last_result = "FAIL"

    errors_sample = errors[:10] if errors else []
    data = {
        "last_run_at_utc": now,
        "last_result": last_result,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "errors_sample": errors_sample,
    }
    path = _mark_refresh_state_path()
    try:
        from app.core.io.atomic import atomic_write_json
        atomic_write_json(path, data, indent=0)
    except Exception as e:
        logger.warning("[MARK_REFRESH] Failed to write state: %s", e)


def load_mark_refresh_state() -> Optional[Dict[str, Any]]:
    """Load mark refresh state for system health. Returns None if file missing."""
    path = _mark_refresh_state_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug("Failed to load mark_refresh_state: %s", e)
        return None


def maybe_append_mark_refresh_failed_notification(updated_count: int, errors: List[str]) -> None:
    """
    On FAIL (updated_count==0 and errors): append DATA_HEALTH subtype MARK_REFRESH_FAILED, throttled 1/hr.
    """
    global _LAST_MARK_REFRESH_FAIL_NOTIFIED_AT
    if updated_count > 0 or not errors:
        return
    import time as _time
    now_ts = _time.time()
    if _LAST_MARK_REFRESH_FAIL_NOTIFIED_AT is not None and (now_ts - _LAST_MARK_REFRESH_FAIL_NOTIFIED_AT) < _MARK_REFRESH_THROTTLE_SEC:
        return

    try:
        from app.api.notifications_store import append_notification
        summary = "; ".join(e[:80] for e in errors[:3])
        append_notification(
            severity="ERROR",
            ntype="DATA_HEALTH",
            message=f"Mark refresh failed: {summary}"[:500],
            symbol=None,
            details={"error_count": len(errors), "errors_sample": errors[:5]},
            subtype="MARK_REFRESH_FAILED",
        )
        _LAST_MARK_REFRESH_FAIL_NOTIFIED_AT = now_ts
    except Exception as e:
        logger.warning("[MARK_REFRESH] Failed to append notification: %s", e)
