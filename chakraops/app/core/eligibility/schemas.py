# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Eligibility trace schema (dict-based for JSON persistence)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_eligibility_trace(
    symbol: str,
    mode_decision: str,
    regime: str,
    timeframe_used: str,
    computed: Dict[str, Any],
    rule_checks: List[Dict[str, Any]],
    rejection_reason_codes: List[str],
    as_of: Optional[str] = None,
    primary_reason_code: Optional[str] = None,
    all_reason_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the canonical eligibility_trace dict for persistence and API. Phase 5.1: rule_checks with reason_code; primary_reason_code; all_reason_codes."""
    out = {
        "symbol": symbol,
        "mode_decision": mode_decision,
        "regime": regime,
        "timeframe_used": timeframe_used,
        "as_of": as_of,
        "computed": computed,
        "rule_checks": rule_checks,
        "rejection_reason_codes": rejection_reason_codes,
        "primary_reason_code": primary_reason_code,
        "all_reason_codes": all_reason_codes if all_reason_codes is not None else rejection_reason_codes,
    }
    if computed:
        out["rsi14"] = computed.get("RSI14")
        out["ema20"] = computed.get("EMA20")
        out["ema50"] = computed.get("EMA50")
        out["atr_pct"] = computed.get("ATR_pct")
        out["distance_to_support_pct"] = computed.get("distance_to_support_pct")
        out["distance_to_resistance_pct"] = computed.get("distance_to_resistance_pct")
        # Phase 5.0: swing_cluster S/R
        out["method"] = computed.get("method")
        out["window"] = computed.get("window")
        out["k"] = computed.get("k")
        out["tolerance_used"] = computed.get("tolerance_used")
        out["swing_high_count"] = computed.get("swing_high_count")
        out["swing_low_count"] = computed.get("swing_low_count")
        out["cluster_count"] = computed.get("cluster_count")
        out["support_level"] = computed.get("support_level")
        out["resistance_level"] = computed.get("resistance_level")
    return out


def computed_values(
    rsi14: Optional[float],
    ema20: Optional[float],
    ema50: Optional[float],
    ema200: Optional[float],
    atr14: Optional[float],
    atr_pct: Optional[float],
    pivots: Optional[Dict[str, float]],
    swing_high: Optional[float],
    swing_low: Optional[float],
    distance_to_support_pct: Optional[float],
    distance_to_resistance_pct: Optional[float],
    close: Optional[float],
) -> Dict[str, Any]:
    """Computed indicator/level values for the trace."""
    return {
        "RSI14": rsi14,
        "EMA20": ema20,
        "EMA50": ema50,
        "EMA200": ema200,
        "ATR14": atr14,
        "ATR_pct": atr_pct,
        "pivots": pivots or {},
        "swing_high": swing_high,
        "swing_low": swing_low,
        "distance_to_support_pct": distance_to_support_pct,
        "distance_to_resistance_pct": distance_to_resistance_pct,
        "close": close,
    }


def rule_check(
    name: str,
    passed: bool,
    value: Any = None,
    threshold: Any = None,
    reason_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Single rule check entry. Phase 5.1: actual (alias value), reason_code."""
    out: Dict[str, Any] = {"name": name, "passed": passed}
    if value is not None:
        out["value"] = value
        out["actual"] = value
    if threshold is not None:
        out["threshold"] = threshold
    if reason_code is not None:
        out["reason_code"] = reason_code
    return out
