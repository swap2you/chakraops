# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS data health: sticky status (UNKNOWN/OK/WARN/DOWN), last_success_at, persistence. Used by /api/ops/data-health and startup self-check.

Phase 8B semantics:
- UNKNOWN: no successful ORATS call has ever occurred.
- OK: last_success_at within evaluation window.
- WARN: last_success_at beyond evaluation window (stale).
- DOWN: last attempt failed and no success within window (or never succeeded).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory state (single process). Persisted to file for stickiness across restarts.
_DATA_STATUS: str = "UNKNOWN"  # OK | DEGRADED | DOWN (raw from last probe)
_LAST_SUCCESS_AT: Optional[str] = None  # ISO
_LAST_ATTEMPT_AT: Optional[str] = None  # ISO — every attempt
_LAST_ERROR_AT: Optional[str] = None
_LAST_ERROR_REASON: Optional[str] = None
_AVG_LATENCY_SECONDS: Optional[float] = None
_LATENCY_SAMPLES: list = []
_ENTITLEMENT: str = "UNKNOWN"  # LIVE | DELAYED | UNKNOWN
_MAX_LATENCY_SAMPLES = 20

# Persistence path (Phase 8B)
def _data_health_state_path() -> Path:
    out = Path(__file__).resolve().parents[2] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "data_health_state.json"


def _evaluation_window_minutes() -> int:
    try:
        from app.core.config.eval_config import EVALUATION_QUOTE_WINDOW_MINUTES
        return EVALUATION_QUOTE_WINDOW_MINUTES
    except Exception:
        return 30


def _load_persisted_state() -> None:
    """Load persisted state so status is sticky across restarts."""
    global _DATA_STATUS, _LAST_SUCCESS_AT, _LAST_ATTEMPT_AT, _LAST_ERROR_AT, _LAST_ERROR_REASON, _AVG_LATENCY_SECONDS, _ENTITLEMENT
    path = _data_health_state_path()
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _LAST_SUCCESS_AT = data.get("last_success_at")
        _LAST_ATTEMPT_AT = data.get("last_attempt_at")
        _LAST_ERROR_AT = data.get("last_error_at")
        _LAST_ERROR_REASON = data.get("last_error_reason")
        _AVG_LATENCY_SECONDS = data.get("avg_latency_seconds")
        _ENTITLEMENT = data.get("entitlement", "UNKNOWN")
        raw = data.get("status")
        if raw in ("OK", "DEGRADED", "DOWN"):
            _DATA_STATUS = raw
        # else keep UNKNOWN
    except Exception as e:
        logger.debug("Failed to load data_health_state: %s", e)


def _persist_state() -> None:
    """Write current state to file."""
    path = _data_health_state_path()
    try:
        data = {
            "last_success_at": _LAST_SUCCESS_AT,
            "last_attempt_at": _LAST_ATTEMPT_AT,
            "last_error_at": _LAST_ERROR_AT,
            "last_error_reason": _LAST_ERROR_REASON,
            "avg_latency_seconds": _AVG_LATENCY_SECONDS,
            "entitlement": _ENTITLEMENT,
            "status": _DATA_STATUS,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
    except Exception as e:
        logger.debug("Failed to persist data_health_state: %s", e)


def _compute_sticky_status() -> str:
    """Phase 8B: UNKNOWN only if no success ever; OK if within window; WARN if stale; DOWN if never succeeded or recent failure."""
    if _LAST_SUCCESS_AT is None and _LAST_ERROR_AT is None:
        return "UNKNOWN"
    if _LAST_SUCCESS_AT is None:
        return "DOWN"
    try:
        success_dt = datetime.fromisoformat(_LAST_SUCCESS_AT.replace("Z", "+00:00"))
        window_min = _evaluation_window_minutes()
        age_minutes = (datetime.now(timezone.utc) - success_dt).total_seconds() / 60
        if age_minutes <= window_min:
            return "OK"
        return "WARN"
    except Exception:
        return "OK" if _LAST_SUCCESS_AT else "UNKNOWN"


def _attempt_live_summary() -> None:
    """Call probe_orats_live(SPY) from unified ORATS Live client; set status OK or DOWN."""
    global _DATA_STATUS, _LAST_SUCCESS_AT, _LAST_ATTEMPT_AT, _LAST_ERROR_AT, _LAST_ERROR_REASON, _AVG_LATENCY_SECONDS, _LATENCY_SAMPLES, _ENTITLEMENT
    from app.core.data.orats_client import probe_orats_live, OratsUnavailableError
    now = datetime.now(timezone.utc).isoformat()
    _LAST_ATTEMPT_AT = now
    try:
        t0 = time.perf_counter()
        result = probe_orats_live("SPY")
        elapsed = time.perf_counter() - t0
        if not result or not result.get("ok") or result.get("row_count", 0) == 0:
            _DATA_STATUS = "DOWN"
            _LAST_ERROR_AT = now
            _LAST_ERROR_REASON = "ORATS returned empty or invalid probe result for SPY"
            return
        _DATA_STATUS = "OK"
        _LAST_SUCCESS_AT = now
        _LAST_ERROR_REASON = None
        _ENTITLEMENT = "LIVE"
        _LATENCY_SAMPLES.append(elapsed)
        if len(_LATENCY_SAMPLES) > _MAX_LATENCY_SAMPLES:
            _LATENCY_SAMPLES.pop(0)
        _AVG_LATENCY_SECONDS = sum(_LATENCY_SAMPLES) / len(_LATENCY_SAMPLES) if _LATENCY_SAMPLES else elapsed
    except OratsUnavailableError as e:
        _DATA_STATUS = "DOWN"
        _LAST_ERROR_AT = now
        _LAST_ERROR_REASON = f"HTTP {e.http_status} — {e.response_snippet[:150]}"
    except Exception as e:
        _DATA_STATUS = "DOWN"
        _LAST_ERROR_AT = now
        _LAST_ERROR_REASON = str(e)[:500]
    _persist_state()


def _data_health_state() -> Dict[str, Any]:
    """Current state with sticky status (UNKNOWN/OK/WARN/DOWN)."""
    status = _compute_sticky_status()
    return {
        "provider": "ORATS",
        "status": status,
        "last_attempt_at": _LAST_ATTEMPT_AT,
        "last_success_at": _LAST_SUCCESS_AT,
        "last_error_at": _LAST_ERROR_AT,
        "last_error_reason": _LAST_ERROR_REASON,
        "avg_latency_seconds": round(_AVG_LATENCY_SECONDS, 3) if _AVG_LATENCY_SECONDS is not None else None,
        "entitlement": _ENTITLEMENT,
        "sample_symbol": "SPY",
        "evaluation_window_minutes": _evaluation_window_minutes(),
    }


def get_data_health() -> Dict[str, Any]:
    """Sticky data health: load persisted state, return status (UNKNOWN/OK/WARN/DOWN). Probe only when UNKNOWN or when caller needs refresh."""
    _load_persisted_state()
    status = _compute_sticky_status()
    if status == "UNKNOWN":
        _attempt_live_summary()
    return _data_health_state()


def _record_success(latency_seconds: float) -> None:
    global _DATA_STATUS, _LAST_SUCCESS_AT, _AVG_LATENCY_SECONDS, _LATENCY_SAMPLES, _ENTITLEMENT
    _DATA_STATUS = "OK"
    _LAST_SUCCESS_AT = datetime.now(timezone.utc).isoformat()
    _ENTITLEMENT = "LIVE"  # We use api.orats.io/datav2/live
    _LATENCY_SAMPLES.append(latency_seconds)
    if len(_LATENCY_SAMPLES) > _MAX_LATENCY_SAMPLES:
        _LATENCY_SAMPLES.pop(0)
    _AVG_LATENCY_SECONDS = sum(_LATENCY_SAMPLES) / len(_LATENCY_SAMPLES) if _LATENCY_SAMPLES else None
    _persist_state()


def _record_error(reason: str) -> None:
    global _DATA_STATUS, _LAST_ERROR_AT, _LAST_ERROR_REASON
    _DATA_STATUS = "DOWN"
    _LAST_ERROR_AT = datetime.now(timezone.utc).isoformat()
    _LAST_ERROR_REASON = reason[:500] if reason else None
    _persist_state()


def run_orats_startup_self_check() -> bool:
    """Run live attempt (probe_orats_live SPY). On failure: DATA_STATUS=DOWN, return False."""
    from app.core.data.orats_client import ORATS_BASE
    logger.info("ORATS startup: base=%s (redacted), live probe SPY", ORATS_BASE)
    _attempt_live_summary()
    if _DATA_STATUS != "OK":
        logger.error("ORATS startup self-check FAILED: %s (DATA_STATUS=DOWN)", _LAST_ERROR_REASON)
        return False
    logger.info("ORATS startup self-check OK: status=OK")
    return True


def refresh_live_data() -> Dict[str, Any]:
    """Pull fresh ORATS data via probe_orats_live(SPY). Raises on failure. No fallbacks."""
    from app.core.data.orats_client import probe_orats_live, OratsUnavailableError
    start = time.perf_counter()
    result = probe_orats_live("SPY")
    elapsed = time.perf_counter() - start
    if not result or not result.get("ok") or result.get("row_count", 0) == 0:
        _record_error("refresh_live_data: empty probe result for SPY")
        raise OratsUnavailableError(
            "ORATS returned empty data for SPY",
            http_status=200,
            response_snippet="empty",
            endpoint="/live/strikes",
            symbol="SPY",
        )
    _record_success(elapsed)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "fetched_at": now,
        "data_latency_seconds": round(elapsed, 3),
        "status": "OK",
    }


# Universe symbols loaded from config/universe.csv (single source of truth).
def _load_universe_symbols() -> List[str]:
    """Load symbols from config/universe.csv. Raises RuntimeError if file missing or empty."""
    import csv
    import os
    csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "universe.csv")
    csv_path = os.path.normpath(csv_path)
    if not os.path.isfile(csv_path):
        raise RuntimeError(f"Universe CSV not found: {csv_path}")
    symbols = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = (row.get("Symbol") or "").strip().upper()
            if sym and sym not in symbols:
                symbols.append(sym)
    if not symbols:
        raise RuntimeError(f"Universe CSV is empty: {csv_path}")
    return symbols

# Load persisted state at import so snapshot and other readers see sticky state (Phase 8B)
_load_persisted_state()

UNIVERSE_SYMBOLS: List[str] = _load_universe_symbols()


def _extract_last_price(row: Dict[str, Any]) -> Optional[float]:
    """Extract last/close/stock price from ORATS summary row if present."""
    if not isinstance(row, dict):
        return None
    for key in ("stockPrice", "closePrice", "close", "last", "underlyingPrice"):
        v = row.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def fetch_universe_from_orats() -> Dict[str, Any]:
    """
    Fetch universe from ORATS Live (same source as probe_orats_live) for UNIVERSE_SYMBOLS. Returns:
    - symbols: list of { symbol, source, last_price, fetched_at, exclusion_reason (null for success) }
    - excluded: list of { symbol, exclusion_reason } for symbols that failed
    - all_failed: True if every symbol failed
    - updated_at: ISO timestamp of fetch
    """
    from app.core.data.orats_client import get_orats_live_summaries, OratsUnavailableError
    updated_at = datetime.now(timezone.utc).isoformat()
    symbols_out: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for ticker in UNIVERSE_SYMBOLS:
        try:
            data = get_orats_live_summaries(ticker.upper(), timeout_sec=10.0)
            if not data or (isinstance(data, list) and len(data) == 0):
                excluded.append({"symbol": ticker, "exclusion_reason": "ORATS returned empty data"})
                continue
            first = data[0] if isinstance(data, list) else None
            if not isinstance(first, dict):
                excluded.append({"symbol": ticker, "exclusion_reason": "ORATS response shape invalid"})
                continue
            last_price = _extract_last_price(first)
            symbols_out.append({
                "symbol": ticker,
                "source": "orats",
                "last_price": last_price,
                "fetched_at": updated_at,
                "exclusion_reason": None,
            })
        except OratsUnavailableError as e:
            excluded.append({"symbol": ticker, "exclusion_reason": f"ORATS error: {e.http_status} — {e.response_snippet[:100]}"})
        except Exception as e:
            excluded.append({"symbol": ticker, "exclusion_reason": str(e)[:200]})
    return {
        "symbols": symbols_out,
        "excluded": excluded,
        "all_failed": len(symbols_out) == 0,
        "updated_at": updated_at,
    }
