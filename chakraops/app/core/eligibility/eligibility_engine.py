# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Eligibility gate. Runs before Stage-2; outputs mode CSP | CC | NONE."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.eligibility import candles as candles_mod
from app.core.eligibility.config import (
    ATR_PERIOD,
    CSP_RSI_MAX,
    CSP_RSI_MIN,
    CC_RSI_MAX,
    CC_RSI_MIN,
    EMA_FAST,
    EMA_MID,
    EMA_SLOW,
    MAX_ATR_PCT,
    RSI_PERIOD,
    RESIST_NEAR_PCT,
    S_R_ATR_MULT,
    S_R_PCT_TOL,
    SUPPORT_NEAR_PCT,
    SWING_CLUSTER_WINDOW,
    SWING_FRACTAL_K,
    SWING_LOOKBACK,
)
from app.core.eligibility.indicators import atr, atr_pct, ema, ema_slope, rsi_wilder
from app.core.eligibility.levels import (
    distance_to_resistance_pct,
    distance_to_support_pct,
    pivots_from_candles,
    swing_high,
    swing_low,
)
from app.core.eligibility.swing_cluster import compute_support_resistance
from app.core.eligibility.schemas import (
    build_eligibility_trace,
    computed_values as cv_dict,
    rule_check,
)

logger = logging.getLogger(__name__)

FAIL_NO_CANDLES = "FAIL_NO_CANDLES"
FAIL_NOT_HELD_FOR_CC = "FAIL_NOT_HELD_FOR_CC"
FAIL_NO_HOLDINGS = "FAIL_NO_HOLDINGS"
FAIL_RSI_CSP = "FAIL_RSI_CSP"
FAIL_RSI_CC = "FAIL_RSI_CC"
FAIL_RSI_RANGE = "FAIL_RSI_RANGE"
FAIL_ATR = "FAIL_ATR"
FAIL_ATR_TOO_HIGH = "FAIL_ATR_TOO_HIGH"
FAIL_NEAR_SUPPORT = "FAIL_NEAR_SUPPORT"
FAIL_NOT_NEAR_SUPPORT = "FAIL_NOT_NEAR_SUPPORT"
FAIL_NEAR_RESISTANCE = "FAIL_NEAR_RESISTANCE"
FAIL_NOT_NEAR_RESISTANCE = "FAIL_NOT_NEAR_RESISTANCE"
FAIL_REGIME_CSP = "FAIL_REGIME_CSP"
FAIL_REGIME_CC = "FAIL_REGIME_CC"
FAIL_REGIME_CONFLICT = "FAIL_REGIME_CONFLICT"
FAIL_NO_SUPPORT = "FAIL_NO_SUPPORT"
FAIL_NO_RESISTANCE = "FAIL_NO_RESISTANCE"
WARN_EVENT_RISK = "WARN_EVENT_RISK"


def classify_regime(
    close: List[float],
    ema20: Optional[float],
    ema50: Optional[float],
    ema200: Optional[float],
    ema50_slope: Optional[float],
) -> str:
    """UP: EMA20 > EMA50 > EMA200 and EMA50 slope up; DOWN: opposite; else SIDEWAYS."""
    if ema20 is None or ema50 is None or ema200 is None or not close:
        return "SIDEWAYS"
    slope_ok = ema50_slope is not None and abs(ema50_slope) >= 1e-6
    if ema20 > ema50 > ema200 and (ema50_slope is not None and ema50_slope > 0):
        return "UP"
    if ema20 < ema50 < ema200 and (ema50_slope is not None and ema50_slope < 0):
        return "DOWN"
    return "SIDEWAYS"


def run(
    symbol: str,
    holdings: Optional[Dict[str, int]] = None,
    current_price: Optional[float] = None,
    lookback: int = 255,
) -> tuple[str, Dict[str, Any]]:
    """
    Run eligibility gate. Returns (mode_decision, eligibility_trace).
    mode_decision: "CSP" | "CC" | "NONE".
    CSP and CC mutually exclusive; CSP takes precedence when both eligible.
    """
    sym = (symbol or "").strip().upper()
    holdings = holdings or {}
    shares = int(holdings.get(sym, 0) or 0)
    as_of = datetime.now(timezone.utc).isoformat()

    cands = candles_mod.get_candles(sym, "daily", lookback)
    if not cands:
        trace = build_eligibility_trace(
            symbol=sym,
            mode_decision="NONE",
            regime="UNKNOWN",
            timeframe_used="daily",
            computed={},
            rule_checks=[],
            rejection_reason_codes=[FAIL_NO_CANDLES],
            as_of=as_of,
        )
        return "NONE", trace

    closes = [float(c["close"]) for c in cands if c.get("close") is not None]
    highs = [float(c["high"]) for c in cands if c.get("high") is not None]
    lows = [float(c["low"]) for c in cands if c.get("low") is not None]
    if len(closes) < max(RSI_PERIOD + 1, EMA_SLOW):
        trace = build_eligibility_trace(
            symbol=sym,
            mode_decision="NONE",
            regime="UNKNOWN",
            timeframe_used="daily",
            computed={"close": closes[-1] if closes else None},
            rule_checks=[],
            rejection_reason_codes=[FAIL_NO_CANDLES],
            as_of=as_of,
        )
        return "NONE", trace

    rsi14 = rsi_wilder(closes, RSI_PERIOD)
    ema20 = ema(closes, EMA_FAST)
    ema50 = ema(closes, EMA_MID)
    ema200 = ema(closes, EMA_SLOW)
    atr14 = atr(highs, lows, closes, ATR_PERIOD)
    atr_pct_val = atr_pct(highs, lows, closes, ATR_PERIOD)
    ema50_slope = ema_slope(closes, EMA_MID, 5)

    pivots = pivots_from_candles(cands)
    s1 = pivots.get("S1") if pivots else None
    r1 = pivots.get("R1") if pivots else None
    sw_high = swing_high(cands, SWING_LOOKBACK)
    sw_low = swing_low(cands, SWING_LOOKBACK)
    last_close = closes[-1]

    # Phase 5.0: Primary S/R from swing-cluster (fractal + ATR clustering); pivots kept for trace only
    sc_result = compute_support_resistance(
        cands,
        last_close,
        atr14,
        window=SWING_CLUSTER_WINDOW,
        k=SWING_FRACTAL_K,
        atr_mult=S_R_ATR_MULT,
        pct_tol=S_R_PCT_TOL,
    )
    dist_support = sc_result.get("distance_to_support_pct")
    dist_resist = sc_result.get("distance_to_resistance_pct")
    support_level = sc_result.get("support_level")
    resistance_level = sc_result.get("resistance_level")

    regime = classify_regime(closes, ema20, ema50, ema200, ema50_slope)

    rejections_before_gating: List[str] = []
    # Phase 4.3: Primary regime = weekly; daily must agree
    try:
        from app.core.eligibility.multiframe import get_weekly_regime, daily_weekly_aligned
        weekly_regime = get_weekly_regime(sym, lookback_days=min(400, lookback * 2))
        if not daily_weekly_aligned(regime, weekly_regime):
            regime = "SIDEWAYS"
            rejections_before_gating = [FAIL_REGIME_CONFLICT]
    except Exception as e:
        logger.debug("[eligibility] multiframe check skipped: %s", e)

    computed = cv_dict(
        rsi14=rsi14,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        atr14=atr14,
        atr_pct=atr_pct_val,
        pivots=pivots,
        swing_high=sw_high,
        swing_low=sw_low,
        distance_to_support_pct=dist_support,
        distance_to_resistance_pct=dist_resist,
        close=last_close,
    )
    computed["method"] = sc_result.get("method", "swing_cluster")
    computed["window"] = sc_result.get("window")
    computed["k"] = sc_result.get("k")
    computed["tolerance_used"] = sc_result.get("tolerance_used")
    computed["swing_high_count"] = sc_result.get("swing_high_count")
    computed["swing_low_count"] = sc_result.get("swing_low_count")
    computed["cluster_count"] = sc_result.get("cluster_count")
    computed["support_level"] = sc_result.get("support_level")
    computed["resistance_level"] = sc_result.get("resistance_level")

    rule_checks: List[Dict[str, Any]] = []
    rejections: List[str] = []

    atr_ok = atr_pct_val is not None and atr_pct_val < MAX_ATR_PCT
    rule_checks.append(rule_check("ATR_pct < MAX_ATR_PCT", atr_ok, atr_pct_val, MAX_ATR_PCT))
    if not atr_ok:
        rejections.append(FAIL_ATR)
        rejections.append(FAIL_ATR_TOO_HIGH)

    regime_up = regime == "UP"
    regime_down = regime == "DOWN"
    near_support = dist_support is not None and dist_support <= SUPPORT_NEAR_PCT
    rule_checks.append(rule_check("near_support", near_support, dist_support, SUPPORT_NEAR_PCT))
    if not near_support:
        rejections.append(FAIL_NOT_NEAR_SUPPORT)
        if support_level is None:
            rejections.append(FAIL_NO_SUPPORT)
    rsi_csp_ok = rsi14 is not None and CSP_RSI_MIN <= rsi14 <= CSP_RSI_MAX
    rule_checks.append(rule_check("RSI in [CSP_RSI_MIN, CSP_RSI_MAX]", rsi_csp_ok, rsi14, (CSP_RSI_MIN, CSP_RSI_MAX)))
    if not rsi_csp_ok and rsi14 is not None:
        rejections.append(FAIL_RSI_RANGE)
        rejections.append(FAIL_RSI_CSP)

    csp_eligible = regime_up and near_support and rsi_csp_ok and atr_ok
    if not regime_up and (near_support and rsi_csp_ok and atr_ok):
        rejections.append(FAIL_REGIME_CSP)

    held_ok = shares > 0
    rule_checks.append(rule_check("holdings > 0 for CC", held_ok, shares, 1))
    if not held_ok:
        rejections.append(FAIL_NOT_HELD_FOR_CC)
        rejections.append(FAIL_NO_HOLDINGS)
    near_resist = dist_resist is not None and dist_resist <= RESIST_NEAR_PCT
    rule_checks.append(rule_check("near_resistance", near_resist, dist_resist, RESIST_NEAR_PCT))
    if not near_resist:
        rejections.append(FAIL_NOT_NEAR_RESISTANCE)
        if resistance_level is None:
            rejections.append(FAIL_NO_RESISTANCE)
    rsi_cc_ok = rsi14 is not None and CC_RSI_MIN <= rsi14 <= CC_RSI_MAX
    rule_checks.append(rule_check("RSI in [CC_RSI_MIN, CC_RSI_MAX]", rsi_cc_ok, rsi14, (CC_RSI_MIN, CC_RSI_MAX)))
    if not rsi_cc_ok and rsi14 is not None:
        rejections.append(FAIL_RSI_RANGE)
        rejections.append(FAIL_RSI_CC)

    cc_eligible = regime_down and held_ok and near_resist and rsi_cc_ok and atr_ok
    if held_ok and not regime_down and (near_resist and rsi_cc_ok and atr_ok):
        rejections.append(FAIL_REGIME_CC)

    if rejections_before_gating:
        mode_decision = "NONE"
        rejection_reason_codes = list(dict.fromkeys(rejections_before_gating + rejections))
    elif csp_eligible:
        mode_decision = "CSP"
        rejection_reason_codes = []
    elif cc_eligible:
        mode_decision = "CC"
        rejection_reason_codes = []
    else:
        mode_decision = "NONE"
        rejection_reason_codes = list(dict.fromkeys(rejections))

    trace = build_eligibility_trace(
        symbol=sym,
        mode_decision=mode_decision,
        regime=regime,
        timeframe_used="daily",
        computed=computed,
        rule_checks=rule_checks,
        rejection_reason_codes=rejection_reason_codes,
        as_of=as_of,
    )
    return mode_decision, trace
