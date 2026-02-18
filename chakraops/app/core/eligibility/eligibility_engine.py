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
    ENABLE_INTRADAY_CONFIRMATION,
    INTRADAY_MIN_ROWS,
    INTRADAY_TIMEFRAME,
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

# Phase 21.1: CC requires at least one standard lot (100 shares) to be eligible
CC_MIN_SHARES = 100
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
FAIL_INTRADAY_DATA_MISSING = "FAIL_INTRADAY_DATA_MISSING"
FAIL_INTRADAY_REGIME_CONFLICT = "FAIL_INTRADAY_REGIME_CONFLICT"
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
    # CC eligible only if shares >= CC_MIN_SHARES (one standard lot)
    held_ok_cc = shares >= CC_MIN_SHARES
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
            primary_reason_code=FAIL_NO_CANDLES,
            all_reason_codes=[FAIL_NO_CANDLES],
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
            primary_reason_code=FAIL_NO_CANDLES,
            all_reason_codes=[FAIL_NO_CANDLES],
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

    # Phase 5.1: Rule-by-rule in evaluation order with reason_code
    rule_checks.append(rule_check("CANDLES_PRESENT", True, len(cands), None, reason_code=FAIL_NO_CANDLES))
    rule_checks.append(rule_check("INDICATORS_PRESENT", True, (rsi14 is not None, ema20 is not None), None, reason_code=FAIL_NO_CANDLES))
    multiframe_ok = not rejections_before_gating
    rule_checks.append(rule_check("MULTIFRAME_ALIGNED", multiframe_ok, regime, None, reason_code=FAIL_REGIME_CONFLICT))

    regime_up = regime == "UP"
    regime_down = regime == "DOWN"
    rule_checks.append(rule_check("REGIME_OK_CSP", regime_up, regime, "UP", reason_code=FAIL_REGIME_CSP))
    rule_checks.append(rule_check("REGIME_OK_CC", regime_down, regime, "DOWN", reason_code=FAIL_REGIME_CC))

    held_ok = held_ok_cc  # HOLDINGS_OK for CC: need >= CC_MIN_SHARES
    rule_checks.append(rule_check("HOLDINGS_OK", held_ok, shares, CC_MIN_SHARES, reason_code=FAIL_NO_HOLDINGS))

    support_found = support_level is not None
    resistance_found = resistance_level is not None
    rule_checks.append(rule_check("SUPPORT_FOUND", support_found, support_level, None, reason_code=FAIL_NO_SUPPORT))
    rule_checks.append(rule_check("RESISTANCE_FOUND", resistance_found, resistance_level, None, reason_code=FAIL_NO_RESISTANCE))

    near_support = dist_support is not None and dist_support <= SUPPORT_NEAR_PCT
    rule_checks.append(rule_check("NEAR_SUPPORT", near_support, dist_support, SUPPORT_NEAR_PCT, reason_code=FAIL_NOT_NEAR_SUPPORT))
    if not near_support:
        rejections.append(FAIL_NOT_NEAR_SUPPORT)
        if support_level is None:
            rejections.append(FAIL_NO_SUPPORT)

    near_resist = dist_resist is not None and dist_resist <= RESIST_NEAR_PCT
    rule_checks.append(rule_check("NEAR_RESISTANCE", near_resist, dist_resist, RESIST_NEAR_PCT, reason_code=FAIL_NOT_NEAR_RESISTANCE))
    if not near_resist:
        rejections.append(FAIL_NOT_NEAR_RESISTANCE)
        if resistance_level is None:
            rejections.append(FAIL_NO_RESISTANCE)

    rsi_csp_ok = rsi14 is not None and CSP_RSI_MIN <= rsi14 <= CSP_RSI_MAX
    rule_checks.append(rule_check("RSI_IN_RANGE_CSP", rsi_csp_ok, rsi14, (CSP_RSI_MIN, CSP_RSI_MAX), reason_code=FAIL_RSI_CSP))
    if not rsi_csp_ok and rsi14 is not None:
        rejections.append(FAIL_RSI_RANGE)
        rejections.append(FAIL_RSI_CSP)

    rsi_cc_ok = rsi14 is not None and CC_RSI_MIN <= rsi14 <= CC_RSI_MAX
    rule_checks.append(rule_check("RSI_IN_RANGE_CC", rsi_cc_ok, rsi14, (CC_RSI_MIN, CC_RSI_MAX), reason_code=FAIL_RSI_CC))
    if not rsi_cc_ok and rsi14 is not None:
        rejections.append(FAIL_RSI_RANGE)
        rejections.append(FAIL_RSI_CC)

    atr_ok = atr_pct_val is not None and atr_pct_val < MAX_ATR_PCT
    rule_checks.append(rule_check("ATR_OK", atr_ok, atr_pct_val, MAX_ATR_PCT, reason_code=FAIL_ATR))
    if not atr_ok:
        rejections.append(FAIL_ATR)
        rejections.append(FAIL_ATR_TOO_HIGH)

    csp_eligible = regime_up and near_support and rsi_csp_ok and atr_ok
    if not regime_up and (near_support and rsi_csp_ok and atr_ok):
        rejections.append(FAIL_REGIME_CSP)
    if not held_ok_cc:
        rejections.append(FAIL_NOT_HELD_FOR_CC)
        rejections.append(FAIL_NO_HOLDINGS)
    cc_eligible = regime_down and held_ok_cc and near_resist and rsi_cc_ok and atr_ok
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

    primary_reason_code: Optional[str] = None
    if mode_decision == "NONE":
        for rc in rule_checks:
            if not rc.get("passed", True) and rc.get("reason_code"):
                primary_reason_code = rc["reason_code"]
                break

    # Phase 5.2: Optional intraday confirmation (4H)
    intraday_block: Dict[str, Any] = {
        "enabled": ENABLE_INTRADAY_CONFIRMATION,
        "timeframe": INTRADAY_TIMEFRAME,
        "data_present": False,
        "intraday_regime": None,
        "alignment_pass": None,
        "reason_code": None,
    }
    if ENABLE_INTRADAY_CONFIRMATION and mode_decision in ("CSP", "CC"):
        from app.core.eligibility.providers.intraday_provider import get_intraday_candles
        intraday_candles = get_intraday_candles(sym, INTRADAY_TIMEFRAME, lookback=200)
        if not intraday_candles or len(intraday_candles) < INTRADAY_MIN_ROWS:
            mode_decision = "NONE"
            primary_reason_code = FAIL_INTRADAY_DATA_MISSING
            rejection_reason_codes = list(dict.fromkeys(rejection_reason_codes + [FAIL_INTRADAY_DATA_MISSING]))
            intraday_block["data_present"] = False
            intraday_block["alignment_pass"] = False
            intraday_block["reason_code"] = FAIL_INTRADAY_DATA_MISSING
        else:
            closes_4h = [float(c["close"]) for c in intraday_candles if c.get("close") is not None]
            ema20_4h = ema(closes_4h, EMA_FAST)
            ema50_4h = ema(closes_4h, EMA_MID)
            ema200_4h = ema(closes_4h, EMA_SLOW)
            ema50_slope_4h = ema_slope(closes_4h, EMA_MID, 5)
            intraday_regime = classify_regime(closes_4h, ema20_4h, ema50_4h, ema200_4h, ema50_slope_4h)
            intraday_block["data_present"] = True
            intraday_block["intraday_regime"] = intraday_regime
            conflict = (mode_decision == "CSP" and intraday_regime == "DOWN") or (
                mode_decision == "CC" and intraday_regime == "UP"
            )
            if conflict:
                mode_decision = "NONE"
                primary_reason_code = FAIL_INTRADAY_REGIME_CONFLICT
                rejection_reason_codes = list(dict.fromkeys(rejection_reason_codes + [FAIL_INTRADAY_REGIME_CONFLICT]))
                intraday_block["alignment_pass"] = False
                intraday_block["reason_code"] = FAIL_INTRADAY_REGIME_CONFLICT
            else:
                intraday_block["alignment_pass"] = True

    trace = build_eligibility_trace(
        symbol=sym,
        mode_decision=mode_decision,
        regime=regime,
        timeframe_used="daily",
        computed=computed,
        rule_checks=rule_checks,
        rejection_reason_codes=rejection_reason_codes,
        as_of=as_of,
        primary_reason_code=primary_reason_code,
        all_reason_codes=rejection_reason_codes,
        intraday=intraday_block,
    )
    return mode_decision, trace
