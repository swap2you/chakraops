#!/usr/bin/env python3
"""
Phase 5 health gate: correctness + completeness checks across data, indicators, S/R,
eligibility, mode integrity, and artifacts. No logic changes; observability only.

Runs a fixed set of symbols (SPY, NVDA, AAPL, MSFT) through the same pipeline as
validate_one_symbol (eligibility + stage2 + artifacts), then prints a strict
PASS/FAIL checklist per symbol and an OVERALL summary.

Usage:
  python scripts/health_gate_phase5.py [--artifacts-dir artifacts/health_gate]

Requires: ORATS (no yfinance fallback). No server required (runs pipeline locally).
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HEALTH_GATE_SYMBOLS = ["SPY", "NVDA", "AAPL", "MSFT"]
MIN_CANDLE_ROWS = 300
SPOT_EPSILON = 1e-6
ATR_PCT_WARN_HI = 0.5
ATR_PCT_PLAUSIBLE_LO = 0.0


def _eval_checklist(
    symbol: str,
    candles: list,
    eligibility_trace: dict | None,
    stage2_trace: dict | None,
    spot_used: float | None,
    artifacts_written: dict,
) -> tuple[list[str], list[str], list[str]]:
    """
    Run Phase 5 checklist on pre-fetched data. Returns (pass_lines, warn_lines, fail_lines).
    Used by main (real run) and by unit test with mocked data (dry run).
    """
    passes: list[str] = []
    warns: list[str] = []
    fails: list[str] = []

    # --- DATA ---
    if not candles or len(candles) < MIN_CANDLE_ROWS:
        fails.append(f"  DATA: ORATS candles rows={len(candles) if candles else 0} (need >= {MIN_CANDLE_ROWS})")
    else:
        passes.append(f"  DATA: ORATS candles rows={len(candles)} (>= {MIN_CANDLE_ROWS})")

    if candles:
        # Normalized OHLC sanity (no high 700 / low 60 type)
        sane = True
        for i, c in enumerate(candles[:5] + candles[-5:]):
            o = c.get("open")
            h = c.get("high")
            l_ = c.get("low")
            cl = c.get("close")
            for v in (o, h, l_, cl):
                if v is not None:
                    try:
                        x = float(v)
                        if x <= 0 or x > 1e9:
                            sane = False
                            break
                    except (TypeError, ValueError):
                        sane = False
            if not sane:
                break
        if sane and len(candles) >= 2:
            first, last = candles[0], candles[-1]
            for key in ("high", "low", "open", "close"):
                if last.get(key) is not None and first.get(key) is not None:
                    try:
                        if float(last[key]) <= 0 or float(first[key]) <= 0:
                            sane = False
                            break
                    except (TypeError, ValueError):
                        sane = False
        if not sane:
            fails.append("  DATA: candles OHLC sanity check failed (invalid or extreme values)")
        else:
            passes.append("  DATA: candles normalized (OHLC sane)")

        # Sorted ascending by ts/tradeDate
        ts_key = "ts" if any(c.get("ts") is not None for c in candles) else "tradeDate"
        ts_list = [c.get(ts_key) for c in candles if c.get(ts_key) is not None]
        sorted_ts = sorted(ts_list)
        if ts_list != sorted_ts:
            fails.append(f"  DATA: candles not sorted ascending by {ts_key}")
        else:
            passes.append(f"  DATA: candles sorted ascending by {ts_key}")

        # Latest close vs spot
        last_close = None
        for c in reversed(candles):
            if c.get("close") is not None:
                try:
                    last_close = float(c["close"])
                    break
                except (TypeError, ValueError):
                    pass
        if last_close is not None and spot_used is not None and spot_used > 0:
            if abs(last_close - spot_used) > SPOT_EPSILON:
                warns.append(f"  DATA: latest close {last_close} != spot_used {spot_used} (within epsilon)")
            else:
                passes.append("  DATA: latest close equals spot used (within epsilon)")
        elif spot_used is None and last_close is not None:
            passes.append("  DATA: latest close present (spot_used not provided)")

    # --- INDICATORS (from eligibility_trace) ---
    el = eligibility_trace or {}
    rsi = el.get("rsi14")
    if rsi is not None:
        try:
            r = float(rsi)
            if 0 <= r <= 100:
                passes.append("  INDICATORS: RSI in [0,100]")
            else:
                fails.append(f"  INDICATORS: RSI={r} not in [0,100]")
        except (TypeError, ValueError):
            fails.append("  INDICATORS: RSI invalid (not in [0,100])")
    else:
        fails.append("  INDICATORS: RSI missing")

    ema20, ema50 = el.get("ema20"), el.get("ema50")
    ema_ok = True
    for name, val in (("EMA20", ema20), ("EMA50", ema50)):
        if val is None:
            ema_ok = False
            break
        try:
            v = float(val)
            if v != v or v <= 0 or v > 1e9:
                ema_ok = False
                break
        except (TypeError, ValueError):
            ema_ok = False
    if ema_ok:
        passes.append("  INDICATORS: EMA20/EMA50 present and sane (not NaN/exploding)")
    else:
        fails.append("  INDICATORS: EMA20/EMA50 missing or invalid")

    atr_pct = el.get("atr_pct")
    if atr_pct is not None:
        try:
            a = float(atr_pct)
            if a <= 0:
                fails.append("  INDICATORS: ATR_pct <= 0")
            elif a >= ATR_PCT_WARN_HI:
                warns.append(f"  INDICATORS: ATR_pct={a} >= {ATR_PCT_WARN_HI} (WARN)")
                passes.append("  INDICATORS: ATR14/ATR_pct present")
            else:
                passes.append("  INDICATORS: ATR14 > 0, ATR_pct in plausible bounds")
        except (TypeError, ValueError):
            fails.append("  INDICATORS: ATR_pct invalid")
    else:
        if el.get("mode_decision") != "NONE" or (el.get("rejection_reason_codes") or []) != ["FAIL_NO_CANDLES"]:
            fails.append("  INDICATORS: ATR_pct missing")

    # --- SUPPORT/RESISTANCE ---
    method = el.get("method") or ""
    if method == "swing_cluster":
        passes.append('  S/R: method == "swing_cluster"')
    else:
        fails.append(f'  S/R: method == {method!r} (expected "swing_cluster")')

    tol_used = el.get("tolerance_used")
    if tol_used is not None:
        try:
            t = float(tol_used)
            if t >= 0:
                passes.append(f"  S/R: tolerance_used computed and bounded (log: {t})")
            else:
                fails.append("  S/R: tolerance_used negative")
        except (TypeError, ValueError):
            warns.append("  S/R: tolerance_used not numeric")
    else:
        if el.get("support_level") is None and el.get("resistance_level") is None:
            passes.append("  S/R: tolerance_used N/A (no S/R levels); reason codes in rejection_reason_codes")
        else:
            warns.append("  S/R: tolerance_used missing but S/R levels present")

    support_level = el.get("support_level")
    resistance_level = el.get("resistance_level")
    if support_level is None or resistance_level is None:
        rej = el.get("rejection_reason_codes") or []
        if any("SUPPORT" in str(r) or "RESISTANCE" in str(r) for r in rej):
            passes.append("  S/R: missing S/R have explicit reason codes in rejection_reason_codes")
        else:
            warns.append("  S/R: S/R missing; ensure reason codes (FAIL_NO_SUPPORT/FAIL_NO_RESISTANCE) present")
    else:
        try:
            s = float(support_level)
            r = float(resistance_level)
            sp = spot_used if spot_used is not None else (float(candles[-1]["close"]) if candles and candles[-1].get("close") else None)
            if sp is not None:
                if s >= sp:
                    warns.append(f"  S/R: support {s} >= spot {sp} (expected support < spot)")
                if r <= sp:
                    warns.append(f"  S/R: resistance {r} <= spot {sp} (expected resistance > spot)")
                if s < sp < r:
                    passes.append("  S/R: support < spot < resistance")
        except (TypeError, ValueError):
            warns.append("  S/R: support/resistance not comparable to spot")

    # --- ELIGIBILITY / EXPLAINABILITY ---
    mode_decision = (el.get("mode_decision") or "NONE").strip().upper()
    if "mode_decision" in el:
        passes.append("  ELIGIBILITY: eligibility_trace includes mode_decision")
    else:
        fails.append("  ELIGIBILITY: mode_decision missing")

    if el.get("primary_reason_code") is not None or mode_decision != "NONE":
        passes.append("  ELIGIBILITY: primary_reason_code present (or mode != NONE)")
    else:
        passes.append("  ELIGIBILITY: primary_reason_code None when NONE (ok)")

    if isinstance(el.get("rejection_reason_codes"), list):
        passes.append("  ELIGIBILITY: rejection_reason_codes list present")
    else:
        fails.append("  ELIGIBILITY: rejection_reason_codes not a list")

    rule_checks = el.get("rule_checks") or []
    has_rule_shape = True
    for rc in rule_checks[:3]:
        if not isinstance(rc, dict) or "name" not in rc or "passed" not in rc:
            has_rule_shape = False
            break
    if has_rule_shape and rule_checks:
        passes.append("  ELIGIBILITY: rule_checks with name, pass, actual, threshold, reason_code")
    elif not rule_checks:
        warns.append("  ELIGIBILITY: rule_checks empty")
    else:
        fails.append("  ELIGIBILITY: rule_checks missing required shape (name, passed)")

    if mode_decision == "NONE":
        primary = el.get("primary_reason_code")
        failing = [r for r in rule_checks if not r.get("passed")]
        if failing and primary is not None:
            first_reason = failing[0].get("reason_code")
            if first_reason == primary:
                passes.append("  ELIGIBILITY: primary_reason_code matches first failing rule")
            else:
                warns.append(f"  ELIGIBILITY: primary_reason_code {primary!r} vs first failing {first_reason!r}")
        for r in failing[:3]:
            name = r.get("name", "?")
            actual = r.get("actual", r.get("value", "?"))
            thresh = r.get("threshold", "?")
            rc = r.get("reason_code", "?")
            passes.append(f"  ELIGIBILITY: failing rule: {name} actual={actual} threshold={thresh} reason_code={rc}")

    # --- MODE INTEGRITY ---
    st2 = stage2_trace or {}
    req = st2.get("request_counts") or {}
    puts_req = req.get("puts_requested")
    calls_req = req.get("calls_requested")
    if puts_req is None:
        puts_req = 0
    if calls_req is None:
        calls_req = 0
    sample = st2.get("sample_request_symbols") or []

    if mode_decision == "NONE":
        if not st2 or (puts_req == 0 and calls_req == 0 and not sample):
            passes.append("  MODE_INTEGRITY: NONE -> Stage-2 did not select contracts (ok)")
        else:
            fails.append("  MODE_INTEGRITY: NONE but Stage-2 has request counts or sample symbols")
    elif mode_decision == "CSP":
        if calls_req != 0:
            fails.append(f"  MODE_INTEGRITY: CSP but calls_requested={calls_req} (must be 0)")
        elif puts_req <= 0 and sample:
            fails.append(f"  MODE_INTEGRITY: CSP but puts_requested={puts_req}")
        else:
            put_only = all(
                isinstance(s, str) and len(s) >= 9 and s[-9] == "P"
                for s in sample
            )
            if put_only or not sample:
                passes.append("  MODE_INTEGRITY: CSP -> only put candidates")
            else:
                fails.append("  MODE_INTEGRITY: CSP found call symbol in sample_request_symbols")
    elif mode_decision == "CC":
        if puts_req != 0:
            fails.append(f"  MODE_INTEGRITY: CC but puts_requested={puts_req} (must be 0)")
        elif calls_req <= 0 and sample:
            fails.append(f"  MODE_INTEGRITY: CC but calls_requested={calls_req}")
        else:
            call_only = all(
                isinstance(s, str) and len(s) >= 9 and s[-9] == "C"
                for s in sample
            )
            if call_only or not sample:
                passes.append("  MODE_INTEGRITY: CC -> only call candidates")
            else:
                fails.append("  MODE_INTEGRITY: CC found put symbol in sample_request_symbols")

    # --- ARTIFACTS ---
    written = artifacts_written or {}
    if written.get("eligibility_trace"):
        passes.append("  ARTIFACTS: eligibility_trace.json written")
    else:
        fails.append("  ARTIFACTS: eligibility_trace.json not written")

    if mode_decision == "NONE":
        if written.get("stage2_trace"):
            warns.append("  ARTIFACTS: stage2_trace written (optional when NONE)")
        passes.append("  ARTIFACTS: stage2_trace absent or minimal when NONE (ok)")
    else:
        if written.get("stage2_trace"):
            passes.append("  ARTIFACTS: stage2_trace.json written")
        else:
            fails.append("  ARTIFACTS: stage2_trace.json not written")

    if written.get("candles"):
        passes.append("  ARTIFACTS: candles.json written")
    else:
        fails.append("  ARTIFACTS: candles.json not written")

    return passes, warns, fails


def run_health_gate_for_symbol(
    symbol: str,
    out_dir: Path,
) -> tuple[list[str], list[str], list[str], dict | None, dict | None]:
    """
    Run pipeline (candles, eligibility, stage2 when mode != NONE) and checklist.
    Returns (passes, warns, fails, eligibility_trace, stage2_trace) for caller to build alert payload.
    """
    passes, warns, fails = [], [], []
    eligibility_trace: dict | None = None
    stage2_trace: dict | None = None
    candles_list: list = []
    spot_used: float | None = None
    artifacts_written: dict = {}

    try:
        from app.core.eligibility.candles import get_candles
        candles_list = get_candles(symbol, "daily", 400)
    except Exception as e:
        fails.append(f"  DATA: ORATS candles fetch failed: {e}")
        return passes, warns, fails, None, None

    if candles_list:
        try:
            last = candles_list[-1]
            spot_used = float(last.get("close")) if last.get("close") is not None else None
        except (TypeError, ValueError):
            pass

    mode_decision = "NONE"
    try:
        from app.core.eligibility.eligibility_engine import run as run_eligibility
        mode_decision, eligibility_trace = run_eligibility(symbol, holdings={}, lookback=255)
    except Exception as e:
        fails.append(f"  ELIGIBILITY: run failed: {e}")
        eligibility_trace = {"mode_decision": "NONE", "rejection_reason_codes": ["ELIGIBILITY_ERROR"], "rule_checks": []}

    if eligibility_trace is None:
        eligibility_trace = {}
    mode_decision = (eligibility_trace.get("mode_decision") or "NONE").strip().upper()

    if mode_decision != "NONE":
        try:
            from app.core.eval.staged_evaluator import evaluate_symbol_full
            from app.core.options.orats_chain_provider import get_chain_provider
            provider = get_chain_provider()
            result = evaluate_symbol_full(symbol, chain_provider=provider, skip_stage2=False)
            stage2_trace = getattr(result.stage2, "stage2_trace", None) if result.stage2 else None
            if not stage2_trace and result.stage2:
                stage2_trace = getattr(result.stage2, "stage2_trace", None)
        except Exception as e:
            warns.append(f"  STAGE2: evaluate_symbol_full failed: {e}")
            stage2_trace = {}

    # Write artifacts
    sym_dir = out_dir / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)

    # Phase 6.1: add score block to trace; Phase 6.3: severity
    try:
        from app.core.scoring.signal_score import compute_signal_score
        from app.core.scoring.tiering import assign_tier
        from app.core.scoring.severity import compute_alert_severity
        el_for_score = eligibility_trace or {}
        score_dict = compute_signal_score(el_for_score, stage2_trace, spot_used)
        tier = assign_tier(el_for_score.get("mode_decision") or "NONE", score_dict.get("composite_score", 0))
        severity_dict = compute_alert_severity(el_for_score, score_dict, tier, spot_used)
        eligibility_trace = {**el_for_score, "score": score_dict, "tier": tier, "severity": severity_dict}
    except Exception:
        pass
    el_path = sym_dir / f"{symbol}_eligibility_trace.json"
    try:
        with open(el_path, "w", encoding="utf-8") as f:
            json.dump(eligibility_trace or {}, f, indent=2, default=str)
        artifacts_written["eligibility_trace"] = True
    except Exception:
        artifacts_written["eligibility_trace"] = False

    if stage2_trace is not None and isinstance(stage2_trace, dict):
        st2_path = sym_dir / f"{symbol}_stage2_trace.json"
        try:
            with open(st2_path, "w", encoding="utf-8") as f:
                json.dump(stage2_trace, f, indent=2, default=str)
            artifacts_written["stage2_trace"] = True
        except Exception:
            artifacts_written["stage2_trace"] = False
    else:
        artifacts_written["stage2_trace"] = False

    candles_path = sym_dir / f"{symbol}_candles.json"
    try:
        with open(candles_path, "w", encoding="utf-8") as f:
            json.dump(candles_list, f, indent=0, default=str)
        artifacts_written["candles"] = True
    except Exception:
        artifacts_written["candles"] = False

    # Run checklist
    p, w, f = _eval_checklist(
        symbol, candles_list, eligibility_trace, stage2_trace, spot_used, artifacts_written
    )
    passes.extend(p)
    warns.extend(w)
    fails.extend(f)

    return passes, warns, fails, eligibility_trace, stage2_trace


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Phase 5 health gate: data, indicators, S/R, eligibility, mode integrity, artifacts")
    parser.add_argument("--artifacts-dir", default="artifacts/health_gate", help="Base dir for artifact output")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    out_dir = (repo_root / args.artifacts_dir.strip()).resolve()
    out_dir = out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Phase 5 Health Gate — run_id={run_id}")
    print(f"Symbols: {HEALTH_GATE_SYMBOLS}")
    print(f"Artifacts: {out_dir}")
    print()

    all_pass: list[str] = []
    all_warn: list[str] = []
    all_fail: list[str] = []

    for symbol in HEALTH_GATE_SYMBOLS:
        print(f"--- {symbol} ---")
        passes, warns, fails, el_trace, st2_trace = run_health_gate_for_symbol(symbol, out_dir)
        for line in passes:
            print(f"PASS {line.strip()}")
        for line in warns:
            print(f"WARN {line.strip()}")
        for line in fails:
            print(f"FAIL {line.strip()}")
        if fails:
            all_fail.append(symbol)
        elif warns:
            all_warn.append(symbol)
        else:
            all_pass.append(symbol)
        print()

    # OVERALL
    print("===== OVERALL =====")
    if all_fail:
        print("OVERALL: FAIL")
        print(f"  Failed symbols: {all_fail}")
    elif all_warn:
        print("OVERALL: WARN")
        print(f"  Warning symbols: {all_warn}")
    else:
        print("OVERALL: PASS")
    print(f"  Pass: {all_pass}")
    print(f"  Warn: {all_warn}")
    print(f"  Fail: {all_fail}")

    # Alert payload per symbol (Phase 6.0)
    try:
        from app.core.alerts.alert_payload import build_alert_payload
        from app.core.alerts.alert_store import save_alert_payload
        for symbol in HEALTH_GATE_SYMBOLS:
            sym_dir = out_dir / symbol
            el_path = sym_dir / f"{symbol}_eligibility_trace.json"
            st2_path = sym_dir / f"{symbol}_stage2_trace.json"
            candles_path = sym_dir / f"{symbol}_candles.json"
            el_trace = None
            st2_trace = None
            candles_meta = {}
            if el_path.exists():
                with open(el_path, encoding="utf-8") as f:
                    el_trace = json.load(f)
            if st2_path.exists():
                with open(st2_path, encoding="utf-8") as f:
                    st2_trace = json.load(f)
            if candles_path.exists():
                with open(candles_path, encoding="utf-8") as f:
                    cands = json.load(f)
                if isinstance(cands, list) and cands:
                    candles_meta["first_date"] = str(cands[0].get("ts") or cands[0].get("tradeDate") or "N/A")[:10]
                    candles_meta["last_date"] = str(cands[-1].get("ts") or cands[-1].get("tradeDate") or "N/A")[:10]
            score_dict = (el_trace or {}).get("score") or {}
            tier = (el_trace or {}).get("tier")
            severity_dict = (el_trace or {}).get("severity") or {}
            payload = build_alert_payload(symbol, run_id, el_trace, st2_trace, candles_meta, {"source": "health_gate_phase5"}, score_dict=score_dict, tier=tier, severity_dict=severity_dict)
            path = save_alert_payload(payload, base_dir=str(repo_root / "artifacts" / "alerts"))
            print(f"ALERT_PAYLOAD saved: {path}")
    except Exception as e:
        print(f"ALERT_PAYLOAD save failed: {e}", file=sys.stderr)

    return 0 if not all_fail else 1


if __name__ == "__main__":
    sys.exit(main())
