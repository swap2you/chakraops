# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase UI-1: Run diagnostics persistence.

Stores throughput, cache, budget, and watchdog state for the last completed run.
Written by nightly evaluation; read by /api/eval/latest-run and /api/system/health.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DIAGNOSTICS_FILENAME = "latest_diagnostics.json"


def _diagnostics_path() -> Path:
    """artifacts/runs/latest_diagnostics.json"""
    return Path(__file__).resolve().parents[3] / "artifacts" / "runs" / _DIAGNOSTICS_FILENAME


def save_run_diagnostics(
    run_id: str,
    *,
    wall_time_sec: float = 0,
    requests_estimated: Optional[int] = None,
    max_requests_estimate: Optional[int] = None,
    cache_hit_rate_pct: Optional[float] = None,
    cache_hit_rate_by_endpoint: Optional[Dict[str, Dict[str, Any]]] = None,
    gate_skips_count: int = 0,
    gate_skip_reasons_summary: Optional[str] = None,
    budget_stopped: bool = False,
    budget_warning: Optional[str] = None,
    watchdog_warnings: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Persist run diagnostics for UI and health endpoints.
    Call after a successful run (e.g. nightly) to record throughput/cache/budget.
    """
    path = _diagnostics_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "wall_time_sec": wall_time_sec,
        "requests_estimated": requests_estimated,
        "max_requests_estimate": max_requests_estimate,
        "cache_hit_rate_pct": cache_hit_rate_pct,
        "cache_hit_rate_by_endpoint": cache_hit_rate_by_endpoint or {},
        "gate_skips_count": gate_skips_count,
        "gate_skip_reasons_summary": gate_skip_reasons_summary,
        "budget_stopped": budget_stopped,
        "budget_warning": budget_warning,
        "watchdog_warnings": watchdog_warnings or [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
        f.flush()
    logger.debug("[RUN_DIAGNOSTICS] Wrote %s", path)


def load_run_diagnostics() -> Optional[Dict[str, Any]]:
    """Load persisted diagnostics. Returns None if not found or invalid."""
    path = _diagnostics_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[RUN_DIAGNOSTICS] Failed to read %s: %s", path, e)
        return None
