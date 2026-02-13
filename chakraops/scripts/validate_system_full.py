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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _float_eq(a: Any, b: Any, tol: float = 1e-6) -> bool:
    """True if a and b are equal as floats within tolerance."""
    if a is None and b is None:
        return True
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


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
    parser.add_argument("--daily-summary", action="store_true", help="Send Slack DAILY summary alert")
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

    # Phase 7.2/7.3: Slack SIGNAL alerts (tier A/B, severity READY/NOW, contracts_suggested > 0); structured payload with exit plan
    try:
        from app.core.alerts.slack_dispatcher import route_alert
        from app.core.lifecycle.exit_planner import build_exit_plan
        slack_state_path = repo_root / "artifacts" / "alerts" / "last_sent_state.json"
        results_by_sym = {r["symbol"]: r for r in results}
        for p in ranked:
            tier = (p.get("tier") or "").strip().upper()
            severity = (p.get("severity") or "").strip().upper()
            ctrs = p.get("contracts_suggested")
            if tier in ("A", "B") and severity in ("READY", "NOW") and (ctrs is not None and ctrs > 0):
                sym = (p.get("symbol") or "?").strip().upper()
                res = results_by_sym.get(sym)
                exit_base, exit_ext, t1, t2 = None, None, None, None
                if res:
                    el, st2, cands = res.get("eligibility_trace"), res.get("stage2_trace"), res.get("cands") or []
                    spot = (st2 or {}).get("spot_used") or (el or {}).get("computed", {}).get("close")
                    if not spot and cands:
                        try:
                            spot = float(cands[-1].get("close"))
                        except (TypeError, ValueError):
                            pass
                    candles_meta = {}
                    if cands:
                        candles_meta["first_date"] = str(cands[0].get("ts") or "N/A")[:10]
                        candles_meta["last_date"] = str(cands[-1].get("ts") or "N/A")[:10]
                    ep = build_exit_plan(sym, p.get("mode_decision") or "NONE", spot, el, st2, candles_meta, ACCOUNT_EQUITY_DEFAULT)
                    if ep and ep.get("enabled"):
                        pp = ep.get("premium_plan") or {}
                        sp = ep.get("structure_plan") or {}
                        exit_base, exit_ext = pp.get("base_target_pct"), pp.get("extension_target_pct")
                        t1, t2 = sp.get("T1"), sp.get("T2")
                payload = {
                    "symbol": sym,
                    "tier": tier,
                    "severity": severity,
                    "composite_score": p.get("composite_score"),
                    "strike": p.get("strike"),
                    "dte": p.get("dte"),
                    "delta": p.get("delta"),
                    "capital_required_estimate": p.get("capital_required_estimate"),
                    "exit_base_target_pct": exit_base,
                    "exit_extension_target_pct": exit_ext,
                    "exit_T1": t1,
                    "exit_T2": t2,
                    "mode": p.get("mode_decision"),
                }
                route_alert("SIGNAL", payload, event_key=f"signal:{sym}", state_path=slack_state_path)
    except Exception as e:
        pass  # do not crash; Slack optional

    # Phase 7.0: Exit plan summary (first ranked candidate)
    if ranked and results:
        sym0 = ranked[0].get("symbol")
        res0 = next((r for r in results if r.get("symbol") == sym0), results[0])
        el0 = res0.get("eligibility_trace")
        st2_0 = res0.get("stage2_trace")
        cands0 = res0.get("cands") or []
        spot0 = (st2_0 or {}).get("spot_used") or (el0 or {}).get("computed", {}).get("close")
        if not spot0 and cands0:
            try:
                spot0 = float(cands0[-1].get("close"))
            except (TypeError, ValueError):
                spot0 = None
        candles_meta0 = {}
        if cands0:
            candles_meta0["first_date"] = str(cands0[0].get("ts") or "N/A")[:10]
            candles_meta0["last_date"] = str(cands0[-1].get("ts") or "N/A")[:10]
        from app.core.lifecycle.exit_planner import build_exit_plan
        ep0 = build_exit_plan(sym0, ranked[0].get("mode_decision") or "NONE", spot0, el0, st2_0, candles_meta0, ACCOUNT_EQUITY_DEFAULT)
        print()
        print("===== EXIT PLAN (Phase 7.0) =====")
        if ep0.get("enabled"):
            print(f"  style={ep0.get('summary', {}).get('style', 'N/A')} primary_focus={ep0.get('summary', {}).get('primary_focus', 'N/A')}")
            sp = ep0.get("structure_plan") or {}
            tp = ep0.get("time_plan") or {}
            pp = ep0.get("premium_plan") or {}
            print(f"  base_target_pct={pp.get('base_target_pct')} extension_target_pct={pp.get('extension_target_pct')}")
            print(f"  T1={sp.get('T1')} T2={sp.get('T2')} stop_hint_price={sp.get('stop_hint_price')} dte={tp.get('dte')}")
            if ep0.get("panic_plan", {}).get("panic_flag"):
                print(f"  panic_flag=True reason={ep0['panic_plan'].get('panic_reason')}")
        else:
            print(f"  enabled=False mode={ep0.get('mode')}")

    # Phase 7.1: Position status (open positions from ledger)
    try:
        from app.core.positions.position_ledger import load_open_positions
        from app.core.positions.position_evaluator import evaluate_position, write_evaluation
        ledger_path = repo_root / "artifacts" / "positions" / "open_positions.json"
        open_positions = load_open_positions(ledger_path)
        if open_positions:
            eval_dir = repo_root / "artifacts" / "positions" / "evaluations"
            print()
            print("===== POSITION STATUS =====")
            fmt_ps = "%6s %8s %4s %8s %12s"
            print(fmt_ps % ("symbol", "premium%", "dte", "signal", "reason"))
            print("-" * 48)
            results_by_symbol = {r["symbol"]: r for r in results}
            for pos in open_positions:
                sym = (pos.get("symbol") or "").strip().upper()
                res = results_by_symbol.get(sym)
                spot = None
                bid, ask = None, None
                el, st2, candles_meta = None, None, {}
                if res:
                    st2 = res.get("stage2_trace")
                    el = res.get("eligibility_trace")
                    spot = (st2 or {}).get("spot_used") or (el or {}).get("computed", {}).get("close")
                    if not spot and (res.get("cands")):
                        try:
                            spot = float(res["cands"][-1].get("close"))
                        except (TypeError, ValueError):
                            pass
                    # Resolve bid/ask for exact position contract: selected_trade first, then chain table
                    pos_exp = (pos.get("expiration") or "")[:10]
                    pos_strike = pos.get("strike")
                    option_type = (pos.get("option_type") or "").strip().upper()
                    if not option_type:
                        option_type = "CALL" if (pos.get("mode") or "").strip().upper() == "CC" else "PUT"
                    sel = (st2 or {}).get("selected_trade")
                    if isinstance(sel, dict):
                        sel_exp = (sel.get("exp") or "")[:10] if sel.get("exp") else ""
                        if pos_exp == sel_exp and _float_eq(pos_strike, sel.get("strike")):
                            bid, ask = sel.get("bid"), sel.get("ask")
                    if bid is None or ask is None:
                        from app.core.positions.quote_resolver import find_contract_quote
                        chain_rows = (st2 or {}).get("top_candidates_table") or []
                        quote = find_contract_quote(chain_rows, pos_exp, pos_strike, option_type)
                        if quote:
                            bid, ask = quote.get("bid"), quote.get("ask")
                    if res.get("cands"):
                        candles_meta["first_date"] = str(res["cands"][0].get("ts") or "N/A")[:10]
                        candles_meta["last_date"] = str(res["cands"][-1].get("ts") or "N/A")[:10]
                if spot is None and pos.get("entry_spot") is not None:
                    spot = float(pos["entry_spot"])
                exit_plan = None
                if el is not None and st2 is not None:
                    from app.core.lifecycle.exit_planner import build_exit_plan
                    exit_plan = build_exit_plan(sym, pos.get("mode") or "CSP", spot, el, st2, candles_meta, ACCOUNT_EQUITY_DEFAULT)
                ev = evaluate_position(pos, spot, bid, ask, exit_plan, date.today())
                write_evaluation(ev, eval_dir)
                pct_s = f"{ev['premium_capture_pct']:.2%}" if ev.get("premium_capture_pct") is not None else "N/A"
                dte_s = str(ev["dte"]) if ev.get("dte") is not None else "N/A"
                print(fmt_ps % (sym, pct_s, dte_s, ev.get("exit_signal", "?"), ev.get("exit_reason", "?")))
                # Phase 7.3: Position alerts (POSITION event; routing by exit_priority in slack_dispatcher)
                exit_sig = ev.get("exit_signal")
                if exit_sig in ("EXIT_NOW", "TAKE_PROFIT", "ROLL_SUGGESTED"):
                    try:
                        from app.core.alerts.slack_dispatcher import route_alert
                        route_alert(
                            "POSITION",
                            {
                                "symbol": sym,
                                "mode": (pos.get("mode") or ev.get("mode") or "CSP"),
                                "position_id": pos.get("position_id", ""),
                                "exit_signal": exit_sig,
                                "exit_reason": ev.get("exit_reason"),
                                "exit_priority": ev.get("exit_priority"),
                                "premium_capture_pct": ev.get("premium_capture_pct"),
                                "dte": ev.get("dte"),
                            },
                            event_key=f"position:{pos.get('position_id', '')}",
                            state_path=repo_root / "artifacts" / "alerts" / "last_sent_state.json",
                        )
                    except Exception:
                        pass
        # if no open positions, do nothing (script does not break)
    except Exception as e:
        print(f"POSITION STATUS skipped: {e}", file=sys.stderr)

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
            from app.core.lifecycle.exit_planner import build_exit_plan
            exit_plan_dict = build_exit_plan(
                symbol, r.get("mode_decision") or "NONE", spot, el, st2, candles_meta, ACCOUNT_EQUITY_DEFAULT
            )
            priority_rank = rank_by_symbol.get(symbol, 1)
            payload = build_alert_payload(
                symbol, run_id, el, st2, candles_meta, {"source": "validate_system_full"},
                score_dict=score_dict, tier=tier, priority_rank=priority_rank, severity_dict=severity_dict, sizing_dict=sizing_dict,
                exit_plan_dict=exit_plan_dict,
            )
            path = save_alert_payload(payload, base_dir=str(repo_root / "artifacts" / "alerts"))
            print(f"ALERT_PAYLOAD saved: {path}")
    except Exception as e:
        print(f"ALERT_PAYLOAD save failed: {e}", file=sys.stderr)

    # Phase 7.3: Optional DAILY summary Slack alert (enriched: total_capital_used, exposure_pct, average_premium_capture, exit_alerts_today, top_signals)
    if getattr(args, "daily_summary", False):
        try:
            from app.core.positions.position_ledger import load_open_positions
            from app.core.alerts.slack_dispatcher import route_alert
            open_positions = load_open_positions(repo_root / "artifacts" / "positions" / "open_positions.json")
            top5 = ranked[:5] if ranked else []
            top_signals = [{"symbol": p.get("symbol"), "tier": p.get("tier"), "severity": p.get("severity")} for p in top5]
            total_capital_used = None
            for pos in open_positions:
                strike = pos.get("strike")
                contracts = pos.get("contracts") or 1
                if strike is not None:
                    cap = float(strike) * 100 * int(contracts)
                    total_capital_used = (total_capital_used or 0) + cap
            account_equity = getattr(args, "account_equity", None) or ACCOUNT_EQUITY_DEFAULT
            exposure_pct = None
            if total_capital_used is not None and account_equity and float(account_equity) > 0:
                exposure_pct = 100.0 * total_capital_used / float(account_equity)
            average_premium_capture = None
            exit_alerts_today = 0
            eval_dir = repo_root / "artifacts" / "positions" / "evaluations"
            if eval_dir.exists():
                import json as _json
                captures = []
                for f in eval_dir.glob("*.json"):
                    try:
                        with open(f, encoding="utf-8") as _f:
                            ev = _json.load(_f)
                        pct = ev.get("premium_capture_pct")
                        if pct is not None:
                            captures.append(pct)
                        if ev.get("exit_signal") in ("EXIT_NOW", "TAKE_PROFIT", "ROLL_SUGGESTED"):
                            exit_alerts_today += 1
                    except (OSError, _json.JSONDecodeError):
                        pass
                if captures:
                    average_premium_capture = sum(captures) / len(captures)
            route_alert(
                "DAILY",
                {
                    "top_signals": top_signals,
                    "top_count": len(top5),
                    "open_positions_count": len(open_positions),
                    "total_capital_used": total_capital_used,
                    "exposure_pct": exposure_pct,
                    "average_premium_capture": average_premium_capture,
                    "exit_alerts_today": exit_alerts_today,
                    "alerts_count": exit_alerts_today,
                },
                event_key="daily:summary",
                state_path=repo_root / "artifacts" / "alerts" / "last_sent_state.json",
            )
        except Exception:
            pass

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
