# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS data health: status (OK/DEGRADED/DOWN), last_success_at, last_error_at, entitlement. Used by /api/ops/data-health and startup self-check."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory state (single process). For multi-worker use file or Redis.
_DATA_STATUS: str = "UNKNOWN"  # OK | DEGRADED | DOWN
_LAST_SUCCESS_AT: Optional[str] = None  # ISO
_LAST_ATTEMPT_AT: Optional[str] = None  # ISO — every attempt
_LAST_ERROR_AT: Optional[str] = None
_LAST_ERROR_REASON: Optional[str] = None
_AVG_LATENCY_SECONDS: Optional[float] = None
_LATENCY_SAMPLES: list = []
_ENTITLEMENT: str = "UNKNOWN"  # LIVE | DELAYED | UNKNOWN
_MAX_LATENCY_SAMPLES = 20


def _attempt_live_summary() -> None:
    """Call probe_orats_live(SPY) from unified ORATS Live client; set status OK or DOWN."""
    global _DATA_STATUS, _LAST_SUCCESS_AT, _LAST_ATTEMPT_AT, _LAST_ERROR_AT, _LAST_ERROR_REASON, _AVG_LATENCY_SECONDS, _LATENCY_SAMPLES, _ENTITLEMENT
    from app.core.orats.orats_client import probe_orats_live, OratsUnavailableError
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


def _data_health_state() -> Dict[str, Any]:
    """Current state only (no new attempt)."""
    return {
        "provider": "ORATS",
        "status": _DATA_STATUS,
        "last_attempt_at": _LAST_ATTEMPT_AT,
        "last_success_at": _LAST_SUCCESS_AT,
        "last_error_at": _LAST_ERROR_AT,
        "last_error_reason": _LAST_ERROR_REASON,
        "avg_latency_seconds": round(_AVG_LATENCY_SECONDS, 3) if _AVG_LATENCY_SECONDS is not None else None,
        "entitlement": _ENTITLEMENT,
        "sample_symbol": "SPY",
    }


def get_data_health() -> Dict[str, Any]:
    """Honest data health: run live attempt (get_live_summary SPY), then return status, last_attempt_at, last_error_reason, sample_symbol."""
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


def _record_error(reason: str) -> None:
    global _DATA_STATUS, _LAST_ERROR_AT, _LAST_ERROR_REASON
    _DATA_STATUS = "DOWN"
    _LAST_ERROR_AT = datetime.now(timezone.utc).isoformat()
    _LAST_ERROR_REASON = reason[:500] if reason else None


def run_orats_startup_self_check() -> bool:
    """Run live attempt (probe_orats_live SPY). On failure: DATA_STATUS=DOWN, return False."""
    from app.core.orats.orats_client import ORATS_BASE
    logger.info("ORATS startup: base=%s (redacted), live probe SPY", ORATS_BASE)
    _attempt_live_summary()
    if _DATA_STATUS != "OK":
        logger.error("ORATS startup self-check FAILED: %s (DATA_STATUS=DOWN)", _LAST_ERROR_REASON)
        return False
    logger.info("ORATS startup self-check OK: status=OK")
    return True


def refresh_live_data() -> Dict[str, Any]:
    """Pull fresh ORATS data via probe_orats_live(SPY). Raises on failure. No fallbacks."""
    from app.core.orats.orats_client import probe_orats_live, OratsUnavailableError
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
    from app.core.orats.orats_client import get_orats_live_summaries, OratsUnavailableError
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
