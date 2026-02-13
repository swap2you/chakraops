#!/usr/bin/env python3
"""
Full sequential system validation: ORATS candles, indicators, regime, eligibility, Stage-2.
Uses eligibility mode only (no CLI --mode override). Prints a summary block.

Run after: pip install -e .  (from chakraops root)

Usage:
  python scripts/validate_system_full.py
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Full system validation (ORATS, indicators, regime, eligibility, Stage-2)")
    parser.add_argument("--symbol", default="SPY", help="Symbol to validate (default: SPY)")
    args = parser.parse_args()
    symbol = (args.symbol or "SPY").strip().upper()

    from app.core.eligibility.candles import get_candles
    from app.core.eligibility.indicators import atr, atr_pct, ema, rsi_wilder
    from app.core.eligibility.eligibility_engine import run as run_eligibility, classify_regime
    from app.core.eligibility.config import RSI_PERIOD, EMA_FAST, EMA_MID, ATR_PERIOD

    candles_ok = False
    indicators_ok = False
    regime_ok = False
    eligibility_ok = False
    stage2_ok = False

    lookback = 400

    # 1) Validate ORATS provider
    try:
        cands = get_candles(symbol, "daily", lookback)
        if not cands:
            print("CANDLES: FAIL (no data)")
        else:
            n = len(cands)
            if n < 300:
                print(f"CANDLES: FAIL (rows={n} < 300)")
            else:
                ts_list = [c.get("ts") for c in cands if c.get("ts")]
                sorted_ts = sorted(ts_list)
                if sorted_ts != ts_list:
                    print("CANDLES: FAIL (not sorted ascending)")
                else:
                    candles_ok = True
                    first_date = ts_list[0] if ts_list else "?"
                    last_date = ts_list[-1] if ts_list else "?"
                    print(f"CANDLES: PASS (rows={n}, first={first_date}, last={last_date})")
    except Exception as e:
        print(f"CANDLES: FAIL ({e})")

    if not candles_ok:
        _print_summary(candles_ok, indicators_ok, regime_ok, eligibility_ok, stage2_ok)
        return 1

    cands = get_candles(symbol, "daily", lookback)
    closes = [float(c["close"]) for c in cands if c.get("close") is not None]
    highs = [float(c["high"]) for c in cands if c.get("high") is not None]
    lows = [float(c["low"]) for c in cands if c.get("low") is not None]

    # 2) Validate indicators
    try:
        rsi = rsi_wilder(closes, RSI_PERIOD)
        ema20 = ema(closes, EMA_FAST)
        ema50 = ema(closes, EMA_MID)
        atr14 = atr(highs, lows, closes, ATR_PERIOD)
        if rsi is None or ema20 is None or ema50 is None or atr14 is None:
            print("INDICATORS: FAIL (one or more None)")
        elif not (0 <= rsi <= 100):
            print(f"INDICATORS: FAIL (RSI={rsi} not in [0,100])")
        else:
            indicators_ok = True
            print("INDICATORS: PASS (RSI, EMA20, EMA50, ATR14 present; RSI in [0,100])")
    except Exception as e:
        print(f"INDICATORS: FAIL ({e})")

    # 3) Validate regime (from eligibility engine)
    try:
        from app.core.eligibility.indicators import ema_slope
        from app.core.eligibility.config import EMA_SLOW
        _ema20 = ema(closes, EMA_FAST)
        _ema50 = ema(closes, EMA_MID)
        ema200 = ema(closes, EMA_SLOW)
        ema50_slope = ema_slope(closes, EMA_MID, 5)
        regime = classify_regime(closes, _ema20, _ema50, ema200, ema50_slope)
        if regime not in ("UP", "DOWN", "SIDEWAYS"):
            print(f"REGIME: FAIL (regime={regime!r})")
        else:
            regime_ok = True
            print(f"REGIME: PASS ({regime})")
    except Exception as e:
        print(f"REGIME: FAIL ({e})")

    # 4) Validate eligibility (Phase 5.0: support_level, resistance_level, method, window, tolerance_used)
    try:
        mode_decision, eligibility_trace = run_eligibility(symbol, holdings={}, lookback=255)
        if not eligibility_trace:
            print("ELIGIBILITY: FAIL (no eligibility_trace)")
        elif not isinstance(eligibility_trace.get("rejection_reason_codes"), list):
            print("ELIGIBILITY: FAIL (rejection_reason_codes not a list)")
        else:
            eligibility_ok = True
            print(f"ELIGIBILITY: PASS (mode_decision={mode_decision}, rejection_reason_codes present)")
            sl = eligibility_trace.get("support_level")
            rl = eligibility_trace.get("resistance_level")
            method = eligibility_trace.get("method", "?")
            window = eligibility_trace.get("window", "?")
            tol = eligibility_trace.get("tolerance_used", "?")
            print(f"  support_level={sl} resistance_level={rl} method={method} window={window} tolerance_used={tol}")
            primary = eligibility_trace.get("primary_reason_code")
            print(f"  primary_reason_code={primary}")
            failing = [r for r in eligibility_trace.get("rule_checks") or [] if not r.get("passed")]
            for r in failing[:3]:
                name = r.get("name", "?")
                actual = r.get("actual", r.get("value", "?"))
                thresh = r.get("threshold", "?")
                print(f"  failing: {name} actual={actual} vs threshold={thresh}")
    except Exception as e:
        print(f"ELIGIBILITY: FAIL ({e})")

    # 5) Validate Stage-2 (only when mode_decision != NONE)
    if eligibility_ok and mode_decision and mode_decision != "NONE":
        try:
            from app.core.eval.staged_evaluator import evaluate_symbol_full
            from app.core.options.orats_chain_provider import get_chain_provider
            provider = get_chain_provider()
            result = evaluate_symbol_full(symbol, chain_provider=provider, skip_stage2=False)
            trace = getattr(result.stage2, "stage2_trace", None) or {}
            req_counts = trace.get("request_counts") or {}
            puts_requested = trace.get("puts_requested") or req_counts.get("puts_requested")
            calls_requested = trace.get("calls_requested") or req_counts.get("calls_requested")
            if puts_requested is None:
                counts = getattr(result.stage2, "option_type_counts", None) or {}
                puts_requested = counts.get("puts_seen", counts.get("puts_requested", 0)) or 0
            if calls_requested is None:
                counts = getattr(result.stage2, "option_type_counts", None) or {}
                calls_requested = counts.get("calls_seen", counts.get("calls_requested", 0)) or 0
            if mode_decision == "CSP":
                if puts_requested <= 0:
                    print(f"STAGE2: FAIL (CSP but puts_requested={puts_requested})")
                else:
                    stage2_ok = True
                    print(f"STAGE2: PASS (CSP, puts_requested={puts_requested})")
            elif mode_decision == "CC":
                if calls_requested <= 0:
                    print(f"STAGE2: FAIL (CC but calls_requested={calls_requested})")
                else:
                    stage2_ok = True
                    print(f"STAGE2: PASS (CC, calls_requested={calls_requested})")
            else:
                stage2_ok = True
                print("STAGE2: PASS (mode not CSP/CC, skip check)")
        except Exception as e:
            print(f"STAGE2: FAIL ({e})")
    else:
        stage2_ok = True
        print("STAGE2: PASS (mode_decision is NONE; skip Stage-2 request check)")

    _print_summary(candles_ok, indicators_ok, regime_ok, eligibility_ok, stage2_ok)
    return 0 if all((candles_ok, indicators_ok, regime_ok, eligibility_ok, stage2_ok)) else 1


def _print_summary(
    candles_ok: bool,
    indicators_ok: bool,
    regime_ok: bool,
    eligibility_ok: bool,
    stage2_ok: bool,
) -> None:
    overall = candles_ok and indicators_ok and regime_ok and eligibility_ok and stage2_ok
    print()
    print("===== SYSTEM VALIDATION =====")
    print("CANDLES: PASS" if candles_ok else "CANDLES: FAIL")
    print("INDICATORS: PASS" if indicators_ok else "INDICATORS: FAIL")
    print("REGIME: PASS" if regime_ok else "REGIME: FAIL")
    print("ELIGIBILITY: PASS" if eligibility_ok else "ELIGIBILITY: FAIL")
    print("STAGE2: PASS" if stage2_ok else "STAGE2: FAIL")
    print("OVERALL: PASS" if overall else "OVERALL: FAIL")


if __name__ == "__main__":
    sys.exit(main())
