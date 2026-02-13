#!/usr/bin/env python3
"""
Full sequential system validation: ORATS candles, indicators, regime, eligibility, Stage-2.
Uses eligibility mode only (no CLI --mode override). Prints a summary block.
Phase 6.1/6.2: scoring, tiering, ranking (informational only). Top 10 candidates when --symbols.

Run after: pip install -e .  (from chakraops root)

Usage:
  python scripts/validate_system_full.py
  python scripts/validate_system_full.py --symbols SPY,NVDA,AAPL,MSFT
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _run_one_symbol(symbol: str, lookback: int = 400) -> Dict[str, Any]:
    """Run validation for one symbol. Returns result dict with ok flags, traces, and payload for ranking."""
    from app.core.eligibility.candles import get_candles
    from app.core.eligibility.indicators import atr, atr_pct, ema, rsi_wilder
    from app.core.eligibility.eligibility_engine import run as run_eligibility, classify_regime
    from app.core.eligibility.config import RSI_PERIOD, EMA_FAST, EMA_MID, ATR_PERIOD

    out: Dict[str, Any] = {
        "symbol": symbol,
        "candles_ok": False,
        "indicators_ok": False,
        "regime_ok": False,
        "eligibility_ok": False,
        "stage2_ok": False,
        "eligibility_trace": None,
        "stage2_trace": None,
        "cands": [],
        "mode_decision": "NONE",
    }

    try:
        cands = get_candles(symbol, "daily", lookback)
    except Exception as e:
        print(f"[{symbol}] CANDLES: FAIL ({e})")
        return out

    if not cands:
        print(f"[{symbol}] CANDLES: FAIL (no data)")
        return out
    n = len(cands)
    if n < 300:
        print(f"[{symbol}] CANDLES: FAIL (rows={n} < 300)")
        return out
    ts_list = [c.get("ts") for c in cands if c.get("ts")]
    if sorted(ts_list) != ts_list:
        print(f"[{symbol}] CANDLES: FAIL (not sorted)")
        return out
    out["candles_ok"] = True
    out["cands"] = cands
    print(f"[{symbol}] CANDLES: PASS (rows={n})")

    closes = [float(c["close"]) for c in cands if c.get("close") is not None]
    highs = [float(c["high"]) for c in cands if c.get("high") is not None]
    lows = [float(c["low"]) for c in cands if c.get("low") is not None]

    try:
        rsi = rsi_wilder(closes, RSI_PERIOD)
        ema20 = ema(closes, EMA_FAST)
        ema50 = ema(closes, EMA_MID)
        atr14 = atr(highs, lows, closes, ATR_PERIOD)
        if rsi is None or ema20 is None or ema50 is None or atr14 is None:
            print(f"[{symbol}] INDICATORS: FAIL")
        elif not (0 <= rsi <= 100):
            print(f"[{symbol}] INDICATORS: FAIL (RSI={rsi})")
        else:
            out["indicators_ok"] = True
            print(f"[{symbol}] INDICATORS: PASS")
    except Exception as e:
        print(f"[{symbol}] INDICATORS: FAIL ({e})")

    try:
        from app.core.eligibility.indicators import ema_slope
        from app.core.eligibility.config import EMA_SLOW
        ema200 = ema(closes, EMA_SLOW)
        ema50_slope = ema_slope(closes, EMA_MID, 5)
        regime = classify_regime(closes, ema(closes, EMA_FAST), ema(closes, EMA_MID), ema200, ema50_slope)
        if regime not in ("UP", "DOWN", "SIDEWAYS"):
            print(f"[{symbol}] REGIME: FAIL ({regime!r})")
        else:
            out["regime_ok"] = True
            print(f"[{symbol}] REGIME: PASS ({regime})")
    except Exception as e:
        print(f"[{symbol}] REGIME: FAIL ({e})")

    try:
        mode_decision, eligibility_trace = run_eligibility(symbol, holdings={}, lookback=255)
        out["mode_decision"] = mode_decision
        out["eligibility_trace"] = eligibility_trace
        if not eligibility_trace or not isinstance(eligibility_trace.get("rejection_reason_codes"), list):
            print(f"[{symbol}] ELIGIBILITY: FAIL")
        else:
            out["eligibility_ok"] = True
            print(f"[{symbol}] ELIGIBILITY: PASS (mode={mode_decision})")
    except Exception as e:
        print(f"[{symbol}] ELIGIBILITY: FAIL ({e})")

    stage2_trace = None
    if out["eligibility_ok"] and mode_decision and mode_decision != "NONE":
        try:
            from app.core.eval.staged_evaluator import evaluate_symbol_full
            from app.core.options.orats_chain_provider import get_chain_provider
            result = evaluate_symbol_full(symbol, chain_provider=get_chain_provider(), skip_stage2=False)
            stage2_trace = getattr(result.stage2, "stage2_trace", None) or {}
            req = stage2_trace.get("request_counts") or {}
            puts_req = req.get("puts_requested") or 0
            calls_req = req.get("calls_requested") or 0
            if mode_decision == "CSP" and puts_req <= 0:
                print(f"[{symbol}] STAGE2: FAIL (puts_requested=0)")
            elif mode_decision == "CC" and calls_req <= 0:
                print(f"[{symbol}] STAGE2: FAIL (calls_requested=0)")
            else:
                out["stage2_ok"] = True
                print(f"[{symbol}] STAGE2: PASS")
        except Exception as e:
            print(f"[{symbol}] STAGE2: FAIL ({e})")
    else:
        out["stage2_ok"] = True
        print(f"[{symbol}] STAGE2: PASS (skip)")

    out["stage2_trace"] = stage2_trace
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Full system validation (ORATS, indicators, regime, eligibility, Stage-2)")
    parser.add_argument("--symbol", default="SPY", help="Single symbol (default: SPY)")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols for ranking (e.g. SPY,NVDA,AAPL,MSFT)")
    args = parser.parse_args()
    if (args.symbols or "").strip():
        symbols = [s.strip().upper() for s in args.symbols.strip().split(",") if s.strip()]
    else:
        symbols = [(args.symbol or "SPY").strip().upper()]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    repo_root = Path(__file__).resolve().parents[1]
    lookback = 400

    results: List[Dict[str, Any]] = []
    for symbol in symbols:
        r = _run_one_symbol(symbol, lookback=lookback)
        results.append(r)

    # Phase 6.1: score + tier per result; Phase 6.3: severity
    from app.core.scoring.signal_score import compute_signal_score
    from app.core.scoring.tiering import assign_tier
    from app.core.scoring.ranking import rank_candidates
    from app.core.scoring.severity import compute_alert_severity
    from app.core.scoring.position_sizing import compute_position_sizing
    from app.core.scoring.config import ACCOUNT_EQUITY_DEFAULT

    candidates: List[Dict[str, Any]] = []
    for r in results:
        el = r.get("eligibility_trace") or {}
        st2 = r.get("stage2_trace") or {}
        spot = st2.get("spot_used") or (el.get("computed") or {}).get("close")
        if spot is None and r.get("cands"):
            try:
                spot = float(r["cands"][-1].get("close"))
            except (TypeError, ValueError):
                pass
        spot_f = float(spot) if spot is not None else 0.0
        score_dict = compute_signal_score(el, st2, spot)
        tier = assign_tier(r.get("mode_decision") or "NONE", score_dict.get("composite_score", 0))
        severity_dict = compute_alert_severity(el, score_dict, tier, spot)
        sizing_dict = compute_position_sizing(r.get("mode_decision") or "NONE", spot_f, st2, ACCOUNT_EQUITY_DEFAULT, holdings_shares=0)
        sel = st2.get("selected_trade") if isinstance(st2, dict) else None
        dist_pct = severity_dict.get("distance_metric_used")
        payload = {
            "symbol": r["symbol"],
            "mode_decision": (r.get("mode_decision") or "NONE").strip().upper(),
            "tier": tier,
            "severity": severity_dict.get("severity"),
            "severity_dict": severity_dict,
            "distance_pct": dist_pct,
            "score": score_dict,
            "composite_score": score_dict.get("composite_score"),
            "notional_pct_of_account": score_dict.get("notional_pct_of_account"),
            "strike": sel.get("strike") if isinstance(sel, dict) else None,
            "delta": sel.get("abs_delta") if isinstance(sel, dict) else None,
            "dte": sel.get("dte") if isinstance(sel, dict) else None,
            "spread_pct": sel.get("spread_pct") if isinstance(sel, dict) else None,
            "expiration": sel.get("exp") if isinstance(sel, dict) else None,
            "contracts_suggested": sizing_dict.get("contracts_suggested"),
            "capital_required_estimate": sizing_dict.get("capital_required_estimate"),
            "capital_pct_of_account": sizing_dict.get("capital_pct_of_account"),
            "limiting_factor": sizing_dict.get("limiting_factor"),
            "sizing_dict": sizing_dict,
        }
        candidates.append(payload)

    ranked = rank_candidates(candidates)

    # Top 10 table (with sizing)
    print()
    print("===== TOP 10 CANDIDATES (ranked) =====")
    fmt = "%4s %6s %4s %4s %8s %12s %8s %8s %6s %10s %4s %10s %10s %14s"
    print(fmt % (
        "rank", "symbol", "mode", "tier", "score", "notional_pct", "strike", "delta", "dte", "spread_pct",
        "ctrs", "cap_req", "cap_pct", "limiting_factor",
    ))
    print("-" * 120)
    for p in ranked[:10]:
        npct = p.get("notional_pct_of_account")
        npct_s = f"{npct:.4f}" if npct is not None else "N/A"
        strike_s = str(p.get("strike")) if p.get("strike") is not None else "N/A"
        delta_s = str(p.get("delta")) if p.get("delta") is not None else "N/A"
        dte_s = str(p.get("dte")) if p.get("dte") is not None else "N/A"
        sp_s = f"{p.get('spread_pct'):.4f}" if p.get("spread_pct") is not None else "N/A"
        score_s = str(p.get("composite_score")) if p.get("composite_score") is not None else "N/A"
        ctrs_s = str(p.get("contracts_suggested")) if p.get("contracts_suggested") is not None else "N/A"
        cap_req = p.get("capital_required_estimate")
        cap_req_s = f"{cap_req:,.0f}" if cap_req is not None else "N/A"
        cap_pct = p.get("capital_pct_of_account")
        cap_pct_s = f"{cap_pct:.4f}" if cap_pct is not None else "N/A"
        lim_s = str(p.get("limiting_factor")) if p.get("limiting_factor") is not None else "N/A"
        print(fmt % (
            p.get("priority_rank", "?"),
            p.get("symbol", "?"),
            p.get("mode_decision", "?"),
            p.get("tier", "?"),
            score_s,
            npct_s,
            strike_s,
            delta_s,
            dte_s,
            sp_s,
            ctrs_s,
            cap_req_s,
            cap_pct_s,
            lim_s,
        ))

    # Phase 6.3: ALERT READINESS (sorted by priority_rank)
    print()
    print("===== ALERT READINESS =====")
    rfmt = "%4s %6s %4s %4s %8s %12s"
    print(rfmt % ("rank", "symbol", "mode", "tier", "severity", "distance_pct"))
    print("-" * 44)
    for p in ranked[:10]:
        dp = p.get("distance_pct")
        dp_s = f"{dp:.6f}" if dp is not None else "N/A"
        print(rfmt % (
            p.get("priority_rank", "?"),
            p.get("symbol", "?"),
            p.get("mode_decision", "?"),
            p.get("tier", "?"),
            p.get("severity", "?"),
            dp_s,
        ))

    # Summary (single-symbol: first result)
    co = results[0]["candles_ok"]
    io = results[0]["indicators_ok"]
    ro = results[0]["regime_ok"]
    eo = results[0]["eligibility_ok"]
    so = results[0]["stage2_ok"]
    _print_summary(co, io, ro, eo, so)

    # Alert payload per symbol with priority_rank from ranking
    rank_by_symbol = {p["symbol"]: p.get("priority_rank", 0) for p in ranked}
    try:
        from app.core.alerts.alert_payload import build_alert_payload
        from app.core.alerts.alert_store import save_alert_payload
        for r in results:
            symbol = r["symbol"]
            el = r.get("eligibility_trace")
            st2 = r.get("stage2_trace")
            cands = r.get("cands") or []
            candles_meta = {}
            if cands:
                candles_meta["first_date"] = str(cands[0].get("ts") or "N/A")[:10]
                candles_meta["last_date"] = str(cands[-1].get("ts") or "N/A")[:10]
            spot = (st2 or {}).get("spot_used") or (el or {}).get("computed", {}).get("close")
            if not spot and cands:
                try:
                    spot = float(cands[-1].get("close"))
                except (TypeError, ValueError):
                    pass
            score_dict = compute_signal_score(el, st2, spot)
            tier = assign_tier(r.get("mode_decision") or "NONE", score_dict.get("composite_score", 0))
            severity_dict = compute_alert_severity(el, score_dict, tier, spot)
            spot_f = float(spot) if spot is not None else 0.0
            sizing_dict = compute_position_sizing(r.get("mode_decision") or "NONE", spot_f, st2, ACCOUNT_EQUITY_DEFAULT, holdings_shares=0)
            priority_rank = rank_by_symbol.get(symbol, 1)
            payload = build_alert_payload(
                symbol, run_id, el, st2, candles_meta, {"source": "validate_system_full"},
                score_dict=score_dict, tier=tier, priority_rank=priority_rank, severity_dict=severity_dict, sizing_dict=sizing_dict,
            )
            path = save_alert_payload(payload, base_dir=str(repo_root / "artifacts" / "alerts"))
            print(f"ALERT_PAYLOAD saved: {path}")
    except Exception as e:
        print(f"ALERT_PAYLOAD save failed: {e}", file=sys.stderr)

    all_ok = all([
        results[0]["candles_ok"], results[0]["indicators_ok"], results[0]["regime_ok"],
        results[0]["eligibility_ok"], results[0]["stage2_ok"],
    ])
    return 0 if all_ok else 1


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
