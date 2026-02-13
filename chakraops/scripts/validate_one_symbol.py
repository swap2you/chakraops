#!/usr/bin/env python3
"""
Single-ticker runtime validation: proves we fetch required fields from ORATS and wire
the same snapshot through all endpoints. Calls API (server must already be running).
Writes JSON artifacts and a human-readable markdown analysis. No cached DB reads.

Usage:
  python scripts/validate_one_symbol.py [--symbol SPY] [--base http://127.0.0.1:8000]

Requires: Server running (e.g. uvicorn app.api.server:app --port 8000). Does NOT auto-start.

Exit codes:
  0 - All required fields present, Stage-1 would PASS (not stale); eligibility/contract checks OK; mode integrity PASS.
  1 - Request/IO error (e.g. connection refused, non-200).
  2 - One or more required fields missing/null (see docs/VALIDATE_ONE_SYMBOL_EXPECTATIONS.md).
  3 - Stage-1 verdict would be BLOCKED (e.g. stale quote_date).
  4 - Contract missing fields (contract_data.available but required chain fields missing).
  5 - Contract unavailable but expected (symbol_eligibility PASS but contract_data not available).
  6 - Mode integrity FAIL (CSP run has calls / CC run has puts).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import json
import time
from datetime import date

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None  # type: ignore


BASE_DEFAULT = "http://127.0.0.1:8000"
SYMBOL_DEFAULT = "SPY"

# Required Stage-1 fields (must match data_requirements.REQUIRED_STAGE1_FIELDS)
REQUIRED_FIELDS = ("price", "bid", "ask", "volume", "quote_date", "iv_rank")
# Snapshot keys: API may expose quote_as_of for display; quote_date is the canonical date
QUOTE_DATE_KEYS = ("quote_date", "quote_as_of")


def _get(url: str, timeout: int = 30) -> tuple[dict | None, int, str]:
    """GET url; return (parsed JSON or None, status_code, error_or_empty)."""
    if urllib is None:
        return None, 0, "urllib not available"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            data = json.loads(body)
            return data, resp.status, ""
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            data = json.loads(body)
        except Exception:
            data = None
        return data, e.code, str(e)
    except urllib.error.URLError as e:
        return None, 0, str(e.reason) if getattr(e, "reason", None) else str(e)
    except json.JSONDecodeError as e:
        return None, 0, f"JSON decode: {e}"
    except Exception as e:
        return None, 0, str(e)


def _get_universe_with_retry(url: str, timeout: int = 10, retry_sleep: float = 1.0) -> tuple[dict | None, int, str]:
    """GET universe URL with 10s timeout; retry once after 1s on failure (resilience, not fallback)."""
    data, code, err = _get(url, timeout=timeout)
    if code == 200 and data is not None:
        return data, code, err
    time.sleep(retry_sleep)
    return _get(url, timeout=timeout)


def _trading_days_since(as_of_date: date | None) -> int | None:
    """Use app's market calendar so staleness matches Stage-1 exactly."""
    if as_of_date is None:
        return None
    try:
        from app.core.environment.market_calendar import trading_days_since as _tds
        return _tds(as_of_date)
    except Exception:
        # Fallback: calendar days (no holiday awareness)
        today = date.today()
        if as_of_date > today:
            return None
        return max(0, (today - as_of_date).days)


def _parse_quote_date(snapshot: dict) -> date | None:
    """Parse quote date from snapshot dict (quote_date or quote_as_of, YYYY-MM-DD)."""
    raw = snapshot.get("quote_date") or snapshot.get("quote_as_of")
    if not raw:
        return None
    s = str(raw).strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, TypeError):
        return None


def _contract_assert(snapshot: dict, missing_reasons: dict, stale_threshold_days: int = 1) -> tuple[list[str], list[str], bool]:
    """
    Returns (missing_fields, block_reasons, is_stale).
    missing_fields: required fields that are null or in missing_reasons.
    block_reasons: human-readable reasons (missing field or stale).
    is_stale: True if quote_date is older than stale_threshold_days.
    """
    missing_fields: list[str] = []
    block_reasons: list[str] = []

    for f in REQUIRED_FIELDS:
        val = snapshot.get(f)
        if f == "quote_date":
            val = val or snapshot.get("quote_as_of")
        # volume=0 is valid; only None/missing counts as missing
        if val is None:
            missing_fields.append(f)
            reason = missing_reasons.get(f) or "not provided"
            block_reasons.append(f"missing: {f} ({reason})")

    quote_parsed = _parse_quote_date(snapshot)
    days_since = _trading_days_since(quote_parsed) if quote_parsed else None
    is_stale = days_since is not None and days_since > stale_threshold_days
    if is_stale and "quote_date" not in missing_fields:
        block_reasons.append(f"DATA_STALE: quote_date is {days_since} day(s) old (threshold {stale_threshold_days})")

    return missing_fields, block_reasons, is_stale


# Required chain fields when contract_data.available (Phase 3.3.1)
REQUIRED_CONTRACT_DATA_KEYS = ("expiration_count", "contract_count", "required_fields_present")


def _eligibility_and_contract_assert(diagnostics: dict) -> tuple[int | None, list[str]]:
    """
    Validate symbol_eligibility, contract_data, contract_eligibility present and,
    when contract_data.available, required chain fields exist.
    Returns (exit_code or None, list of error messages).
    None = no exit; 4 = contract missing fields; 5 = contract unavailable but expected.
    """
    errs: list[str] = []
    if not isinstance(diagnostics, dict):
        return 2, ["diagnostics response is not a dict"]

    # 1) symbol_eligibility present
    se = diagnostics.get("symbol_eligibility")
    if se is None:
        errs.append("symbol_eligibility missing")
    elif not isinstance(se, dict):
        errs.append("symbol_eligibility is not a dict")

    # 2) contract_data present
    cd = diagnostics.get("contract_data")
    if cd is None:
        errs.append("contract_data missing")
    elif not isinstance(cd, dict):
        errs.append("contract_data is not a dict")

    # 3) contract_eligibility present
    ce = diagnostics.get("contract_eligibility")
    if ce is None:
        errs.append("contract_eligibility missing")
    elif not isinstance(ce, dict):
        errs.append("contract_eligibility is not a dict")

    if errs:
        return 2, errs  # required structure missing (symbol_eligibility / contract_data / contract_eligibility)

    # 4) If contract_data.available: check schema. Do NOT treat required_fields_present==False
    #    as hard failure when chain exists - log as WARN and exit 0 (selection may have failed for other reasons).
    available = cd.get("available") is True
    if available:
        for key in REQUIRED_CONTRACT_DATA_KEYS:
            if key not in cd:
                errs.append(f"contract_data.available but missing key: {key}")
        if errs:
            return 4, errs
        # required_fields_present==False: log but do not fail (exit 0) - chain exists, may be selection failure
        if cd.get("required_fields_present") is False:
            return None, ["WARN: contract_data.required_fields_present is False (chain has puts but none with all required fields) - check puts_with_required_fields"]

    # 5) Exit 5 ONLY when chain truly unavailable: Stage-1 PASS but Stage-2 did not run or returned no contracts.
    #    Do NOT exit 5 when contract_data.available=True and contract_eligibility.status=FAIL — that's normal
    #    (chain fetched, but no contract passed filters).
    se_status = (se or {}).get("status") if isinstance(se, dict) else None
    ce_status = (ce or {}).get("status") if isinstance(ce, dict) else None
    if se_status == "PASS" and not available:
        return 5, ["EXIT 5: Stage-1 PASS but chain truly unavailable (contract_data.available=False)"]
    # Log info when chain available but no contract passed (not an error)
    if se_status == "PASS" and available and ce_status == "FAIL":
        return None, []  # INFO handled by caller if desired; no exit

    return None, []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one symbol: call API, save artifacts, run contract assertion. Server must be running."
    )
    parser.add_argument("--symbol", default=SYMBOL_DEFAULT, help=f"Ticker (default: {SYMBOL_DEFAULT})")
    parser.add_argument("--base", default=BASE_DEFAULT, help=f"API base URL (default: {BASE_DEFAULT})")
    parser.add_argument("--mode", choices=("csp", "cc"), default="csp", help="API query only (test); actual mode from eligibility (default: csp)")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    symbol = (args.symbol or SYMBOL_DEFAULT).strip().upper()
    mode = (args.mode or "csp").strip().lower()

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "artifacts" / "validate"
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    build_id_mismatch: bool = False
    build_id_warning_msg: str = ""

    # 0) GET /health for build_id (port/server mismatch guard)
    url_health = f"{base}/health"
    health_data, health_code, _ = _get(url_health, timeout=5)
    if health_code == 200 and health_data:
        server_build_id = health_data.get("build_id") or ""
        local_build_id = ""
        try:
            import subprocess
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if r.returncode == 0 and r.stdout:
                local_build_id = r.stdout.strip()[:12]
        except Exception:
            pass
        if server_build_id and local_build_id and server_build_id != local_build_id:
            build_id_mismatch = True
            build_id_warning_msg = (
                f"WARNING: Server build_id ({server_build_id}) does not match local working tree ({local_build_id}). "
                "Validation may be running against a different code version (e.g. different port or stale server)."
            )
            print(f"\n*** {build_id_warning_msg} ***\n", file=sys.stderr)

    # 1) GET /api/ops/snapshot?symbol=...
    url_snapshot = f"{base}/api/ops/snapshot?symbol={symbol}"
    data_snap, code_snap, err_snap = _get(url_snapshot)
    if code_snap != 200:
        errors.append(f"ops/snapshot: {code_snap} {err_snap or 'non-200'}")
    out_snap = out_dir / f"{symbol}_ops_snapshot.json"
    if data_snap is not None:
        with open(out_snap, "w", encoding="utf-8") as f:
            json.dump(data_snap, f, indent=2)
        print(f"Wrote {out_snap}")
    else:
        print(f"ops/snapshot failed: {err_snap}", file=sys.stderr)

    # 2) GET /api/view/symbol-diagnostics?symbol=...&mode=...
    url_diag = f"{base}/api/view/symbol-diagnostics?symbol={symbol}&mode={mode}"
    data_diag, code_diag, err_diag = _get(url_diag)
    if code_diag != 200:
        errors.append(f"symbol-diagnostics: {code_diag} {err_diag or 'non-200'}")
    out_diag = out_dir / f"{symbol}_symbol_diagnostics.json"
    if data_diag is not None:
        with open(out_diag, "w", encoding="utf-8") as f:
            json.dump(data_diag, f, indent=2)
        print(f"Wrote {out_diag}")
        # Stage-2 trace for harness comparison (Phase 3.2: never null when contract_data available)
        trace = data_diag.get("stage2_trace")
        out_trace = out_dir / f"{symbol}_stage2_trace.json"
        if isinstance(trace, dict):
            to_write = trace
        else:
            # Build minimal trace from diagnostics so file is never "Trace not available" placeholder
            cd = data_diag.get("contract_data") or {}
            stock = data_diag.get("stock") or {}
            opts = data_diag.get("options") or {}
            to_write = {
                "spot_used": cd.get("spot_used") or stock.get("price"),
                "expirations_in_window": opts.get("expirations_count") or [],
                "requested_put_strikes": None,
                "requested_tickers_count": None,
                "sample_request_symbols": [],
                "response_rows": None,
                "otm_puts_in_dte": cd.get("otm_puts_in_dte", 0),
                "otm_puts_in_delta_band": cd.get("otm_puts_in_delta_band", 0),
                "delta_abs_stats_otm_puts": None,
                "sample_otm_puts": [],
                "message": "Minimal trace (validate_one_symbol fallback)",
            }
        with open(out_trace, "w", encoding="utf-8") as f:
            json.dump(to_write, f, indent=2, default=str)
        print(f"Wrote {out_trace}")
        # Phase 4: Persist eligibility_trace
        el_trace = data_diag.get("eligibility_trace")
        if isinstance(el_trace, dict):
            out_el = out_dir / f"{symbol}_eligibility_trace.json"
            with open(out_el, "w", encoding="utf-8") as f:
                json.dump(el_trace, f, indent=2, default=str)
            print(f"Wrote {out_el}")
    else:
        print(f"symbol-diagnostics failed: {err_diag}", file=sys.stderr)

    # 3) GET /api/view/universe (10s timeout, retry once after 1s)
    url_universe = f"{base}/api/view/universe"
    data_univ, code_univ, err_univ = _get_universe_with_retry(url_universe)
    out_univ = out_dir / "universe.json"
    if data_univ is not None:
        with open(out_univ, "w", encoding="utf-8") as f:
            json.dump(data_univ, f, indent=2)
        print(f"Wrote {out_univ}")
    else:
        with open(out_univ, "w", encoding="utf-8") as f:
            json.dump({"error": err_univ or str(code_univ), "symbols": [], "updated_at": None}, f, indent=2)
        print(f"Wrote {out_univ} (universe returned non-200 or invalid JSON)")
    if code_univ != 200:
        errors.append(f"universe: {code_univ} {err_univ or 'non-200'}")

    # --- Candle diagnostics (ORATS daily provider) ---
    candles_list = []
    candles_first_date = "N/A"
    candles_last_date = "N/A"
    try:
        from app.core.eligibility.candles import get_candles
        candles_list = get_candles(symbol, lookback=400)
        if candles_list:
            candles_first_date = str(candles_list[0].get("ts") or "N/A")[:10]
            candles_last_date = str(candles_list[-1].get("ts") or "N/A")[:10]
        out_candles = out_dir / f"{symbol}_candles.json"
        with open(out_candles, "w", encoding="utf-8") as f:
            json.dump(candles_list, f, indent=0, default=str)
        print(f"Wrote {out_candles}")
    except Exception as e:
        print(f"Candle fetch failed: {e}", file=sys.stderr)
    print("\n--- Candle Diagnostics ---")
    print(f"rows={len(candles_list)} first_date={candles_first_date} last_date={candles_last_date}")

    # --- Snapshot for contract checks ---
    snap_obj = (data_snap or {}).get("snapshot")
    if not isinstance(snap_obj, dict):
        snap_obj = (data_diag or {}).get("stock") if data_diag else {}
    if not isinstance(snap_obj, dict):
        snap_obj = {}
    missing_reasons = (data_snap or {}).get("missing_reasons") or (snap_obj.get("missing_reasons") or {})
    missing_reasons = missing_reasons if isinstance(missing_reasons, dict) else {}

    try:
        from app.core.data.data_requirements import STAGE1_STALE_TRADING_DAYS
        stale_threshold = STAGE1_STALE_TRADING_DAYS
    except Exception:
        stale_threshold = 1
    missing_fields, block_reasons, is_stale = _contract_assert(snap_obj, missing_reasons, stale_threshold_days=stale_threshold)

    # --- Markdown analysis ---
    analysis_lines = [
        f"# Validation: {symbol}",
        "",
    ]
    if build_id_mismatch and build_id_warning_msg:
        analysis_lines.append("## ⚠ Build / server mismatch")
        analysis_lines.append("")
        analysis_lines.append(build_id_warning_msg)
        analysis_lines.append("")
    analysis_lines.extend([
        "## Endpoints",
        f"- `GET {url_snapshot}` → {out_snap.name}",
        f"- `GET {url_diag}` → {out_diag.name}",
        f"- `GET {url_universe}` → {out_univ.name}",
        "",
        "## Candle Diagnostics",
        f"- **rows**: {len(candles_list)}",
        f"- **first_date**: {candles_first_date}",
        f"- **last_date**: {candles_last_date}",
        "",
        "## Required fields (Stage-1)",
        f"Expected: {', '.join(REQUIRED_FIELDS)}.",
        "",
    ])
    for f in REQUIRED_FIELDS:
        key = f if f != "quote_date" else ("quote_date / quote_as_of")
        val = snap_obj.get(f) if f != "quote_date" else (snap_obj.get("quote_date") or snap_obj.get("quote_as_of"))
        status = "MISSING" if f in missing_fields else "present"
        analysis_lines.append(f"- **{key}**: {val!r} ({status})")
    analysis_lines.append("")
    analysis_lines.append("## missing_reasons (required fields)")
    if not missing_reasons:
        analysis_lines.append("(empty — expected when ORATS returns all required data)")
    else:
        for k in REQUIRED_FIELDS:
            analysis_lines.append(f"- **{k}**: " + (missing_reasons.get(k) or "—"))
    analysis_lines.append("")
    # Stage-2 /strikes/options telemetry (endpoint and non-null counts)
    cd = (data_diag or {}).get("contract_data") or {}
    opt = (data_diag or {}).get("options") or {}
    tel = cd.get("strikes_options_telemetry") or opt.get("strikes_options_telemetry")
    if tel and isinstance(tel, dict):
        analysis_lines.append("## /strikes/options telemetry")
        analysis_lines.append(f"- **endpoint_used**: {tel.get('endpoint_used', '—')}")
        analysis_lines.append(f"- **requested_tickers_count**: {tel.get('requested_tickers_count', '—')}")
        analysis_lines.append(f"- **response_rows**: {tel.get('response_rows', '—')}")
        analysis_lines.append(f"- **non_null_bidask**: {tel.get('non_null_bidask', '—')}")
        analysis_lines.append(f"- **non_null_oi**: {tel.get('non_null_oi', '—')}")
        analysis_lines.append(f"- **non_null_vol**: {tel.get('non_null_vol', '—')}")
        analysis_lines.append("")
    analysis_lines.append("## Stage-1 verdict")
    if missing_fields:
        analysis_lines.append("**BLOCK** — required field(s) missing: " + ", ".join(missing_fields))
        for r in block_reasons:
            analysis_lines.append(f"- {r}")
    elif is_stale:
        analysis_lines.append("**BLOCK** — quote_date stale")
        for r in block_reasons:
            analysis_lines.append(f"- {r}")
    else:
        analysis_lines.append("**PASS** — all required fields present and quote_date fresh.")
    analysis_lines.append("")

    # Phase 4: Eligibility Block (mode, regime, key indicators, top rejections)
    el_trace = (data_diag or {}).get("eligibility_trace")
    if isinstance(el_trace, dict):
        mode_el = el_trace.get("mode_decision") or "NONE"
        regime_el = el_trace.get("regime") or "—"
        comp = el_trace.get("computed") or {}
        rej = el_trace.get("rejection_reason_codes") or []
        analysis_lines.append("## Eligibility Block (Phase 4)")
        analysis_lines.append("")
        analysis_lines.append(f"- **mode_decision**: {mode_el}")
        analysis_lines.append(f"- **regime**: {regime_el}")
        analysis_lines.append(f"- **RSI14**: {comp.get('RSI14')}")
        analysis_lines.append(f"- **EMA20 / EMA50 / EMA200**: {comp.get('EMA20')} / {comp.get('EMA50')} / {comp.get('EMA200')}")
        analysis_lines.append(f"- **ATR_pct**: {comp.get('ATR_pct')}")
        analysis_lines.append(f"- **distance_to_support_pct**: {comp.get('distance_to_support_pct')}")
        analysis_lines.append(f"- **distance_to_resistance_pct**: {comp.get('distance_to_resistance_pct')}")
        analysis_lines.append(f"- **rejection_reason_codes**: {rej}")
        analysis_lines.append("")
        print("\n--- Eligibility Block ---")
        print(f"mode_decision={mode_el} regime={regime_el}")
        print(f"RSI14={comp.get('RSI14')} EMA20={comp.get('EMA20')} EMA50={comp.get('EMA50')} ATR_pct={comp.get('ATR_pct')}")
        print(f"rejection_reason_codes={rej}")

    # Phase 3.5: Truth Summary + Top Candidates Table
    trace = (data_diag or {}).get("stage2_trace") or {}
    cd = (data_diag or {}).get("contract_data") or {}
    opt = (data_diag or {}).get("options") or {}
    tel = cd.get("strikes_options_telemetry") or opt.get("strikes_options_telemetry") or {}
    req_counts = trace.get("request_counts") or {}
    puts_req = req_counts.get("puts_requested") if "puts_requested" in req_counts else trace.get("puts_requested")
    calls_req = req_counts.get("calls_requested") if "calls_requested" in req_counts else trace.get("calls_requested", 0)
    exp_in_window = trace.get("expirations_in_window") or []
    exp_count = len(exp_in_window) if isinstance(exp_in_window, list) else trace.get("expirations_count") or 0
    delta_stats = trace.get("delta_abs_stats") or trace.get("delta_abs_stats_otm_puts") or opt.get("delta_distribution") or {}
    d_min = delta_stats.get("min_abs_put_delta") or delta_stats.get("min")
    d_med = delta_stats.get("median")
    d_max = delta_stats.get("max_abs_put_delta") or delta_stats.get("max")
    sample_syms = (trace.get("sample_request_symbols") or tel.get("sample_request_symbols") or [])[:5]
    truth_lines = [
        "## Stage-2 Truth Summary (Phase 3.5)",
        "",
        f"- **mode**: {mode.upper()}",
        f"- **spot_used**: {trace.get('spot_used') or cd.get('spot_used')}",
        f"- **expirations_in_window**: count={exp_count}, list={exp_in_window[:10] if isinstance(exp_in_window, list) else exp_in_window}",
        f"- **request_counts**: puts_requested={puts_req}, calls_requested={calls_req}",
        f"- **sample_request_symbols[0:5]**: {sample_syms}",
        f"- **response_rows**: {trace.get('response_rows') or tel.get('response_rows')}",
        f"- **puts_with_required_fields**: {trace.get('puts_with_required_fields') or opt.get('puts_with_required_fields') or cd.get('puts_with_required_fields')}",
        f"- **calls_with_required_fields**: {trace.get('calls_with_required_fields') or opt.get('calls_with_required_fields') or cd.get('calls_with_required_fields')}",
        f"- **otm_puts_in_dte / otm_calls_in_dte**: {trace.get('otm_puts_in_dte') or trace.get('otm_calls_in_dte') or cd.get('otm_puts_in_dte')}",
        f"- **otm_in_delta_band**: {trace.get('otm_puts_in_delta_band') or trace.get('otm_calls_in_delta_band') or trace.get('otm_contracts_in_delta_band') or cd.get('otm_puts_in_delta_band')}",
        f"- **delta_abs_stats**: min={d_min}, median={d_med}, max={d_max}",
    ]
    candidate_trades = (data_diag or {}).get("candidate_trades") or []
    sel_contract = trace.get("selected_contract")
    if candidate_trades:
        truth_lines.append(f"- **selected_trade**: {candidate_trades[0]}")
    elif sel_contract:
        truth_lines.append(f"- **selected_trade**: {sel_contract}")
    else:
        top_rej = trace.get("top_rejection_reason") or (opt.get("top_rejection_reasons") or {}).get("top_rejection_reason")
        sample_rej = trace.get("sample_rejections") or (opt.get("top_rejection_reasons") or {}).get("sample_rejected_candidates") or []
        truth_lines.append(f"- **top_rejection**: {top_rej or 'N/A'}")
        truth_lines.append(f"- **sample_rejections[0:5]**: {sample_rej[:5]}")
    truth_lines.append("")
    analysis_lines.extend(truth_lines)

    # Acceptance Block (Phase 3.6/3.7)
    otm_in_delta = trace.get("otm_puts_in_delta_band") or trace.get("otm_contracts_in_delta_band") or trace.get("otm_calls_in_delta_band") or cd.get("otm_puts_in_delta_band") or cd.get("otm_contracts_in_delta_band") or 0
    sel_trade = trace.get("selected_trade") or trace.get("selected_contract") or (candidate_trades[0] if candidate_trades else None) or sel_contract
    selected_yn = "Y" if sel_trade else "N"
    top_rej = trace.get("top_rejection") or trace.get("top_rejection_reason") or (opt.get("top_rejection_reasons") or {}).get("top_rejection_reason")
    sel_summary = ""
    if sel_trade and isinstance(sel_trade, dict):
        sel_summary = f"strike={sel_trade.get('strike')} exp={sel_trade.get('exp')} bid={sel_trade.get('bid')} abs_delta={sel_trade.get('abs_delta')} oi={sel_trade.get('oi')} spread_pct={sel_trade.get('spread_pct')}"
    elif sel_trade:
        sel_summary = str(sel_trade)[:80]
    acceptance_block = (
        f"## Acceptance Block\n\n"
        f"mode={mode.upper()} | puts_requested={puts_req} | calls_requested={calls_req} | expirations_count={exp_count} | "
        f"response_rows={trace.get('response_rows') or tel.get('response_rows')} | otm_in_delta_band={otm_in_delta} | "
        f"selected? {selected_yn} | top_rejection={top_rej or 'N/A'}"
    )
    if selected_yn == "Y":
        acceptance_block += f"\n  selected: {sel_summary}"
    acceptance_block += "\n"
    analysis_lines.append(acceptance_block)
    print("\n--- Acceptance Block ---")
    print(acceptance_block.strip())

    # Phase 3.8: Mode Integrity — eligibility is single source of truth. Use mode_decision from response, NOT CLI --mode.
    # If eligibility returned NONE, stage2 did not run; skip integrity or pass. Otherwise validate trace matches mode_decision.
    cd_for_integrity = (data_diag or {}).get("contract_data") or {}
    trace_integrity = cd_for_integrity.get("stage2_trace") or trace
    if not isinstance(trace_integrity, dict):
        trace_integrity = {}
    el_trace_integrity = (data_diag or {}).get("eligibility_trace") or {}
    mode_decision_for_integrity = (el_trace_integrity.get("mode_decision") or "").strip().upper()
    if mode_decision_for_integrity not in ("CSP", "CC"):
        mode_decision_for_integrity = ""  # NONE or missing: no stage2 run to validate
    req_counts_integrity = trace_integrity.get("request_counts") or {}
    puts_req_i = req_counts_integrity.get("puts_requested")
    calls_req_i = req_counts_integrity.get("calls_requested")
    if puts_req_i is None:
        puts_req_i = 0
    if calls_req_i is None:
        calls_req_i = 0
    sample_symbols_integrity = trace_integrity.get("sample_request_symbols") or []
    mode_integrity_pass = True
    mode_integrity_fail_reason = None
    has_trace = isinstance(trace_integrity, dict) and (req_counts_integrity or sample_symbols_integrity)
    if has_trace and mode_decision_for_integrity:
        m = mode_decision_for_integrity
        if m == "CSP":
            if calls_req_i != 0:
                mode_integrity_pass = False
                mode_integrity_fail_reason = f"MODE_INTEGRITY_FAIL: CSP found calls_requested={calls_req_i} (must be 0)"
            elif puts_req_i <= 0:
                mode_integrity_pass = False
                mode_integrity_fail_reason = f"MODE_INTEGRITY_FAIL: CSP found puts_requested={puts_req_i} (must be > 0)"
            else:
                for s in sample_symbols_integrity:
                    if isinstance(s, str) and len(s) >= 9 and s[-9] != "P":
                        mode_integrity_pass = False
                        mode_integrity_fail_reason = f"MODE_INTEGRITY_FAIL: CSP found call symbol {s}"
                        break
        elif m == "CC":
            if puts_req_i != 0:
                mode_integrity_pass = False
                mode_integrity_fail_reason = f"MODE_INTEGRITY_FAIL: CC found puts_requested > 0"
            elif calls_req_i <= 0:
                mode_integrity_pass = False
                mode_integrity_fail_reason = f"MODE_INTEGRITY_FAIL: CC found calls_requested={calls_req_i} (must be > 0)"
            else:
                for s in sample_symbols_integrity:
                    if isinstance(s, str) and len(s) >= 9 and s[-9] != "C":
                        mode_integrity_pass = False
                        mode_integrity_fail_reason = f"MODE_INTEGRITY_FAIL: CC found put symbol {s}"
                        break
    first_3 = (trace.get("sample_request_symbols") or [])[:3]
    mode_display = mode_decision_for_integrity or mode.upper()
    mode_integrity_line = (
        f"Mode Integrity: mode={mode_display} (from eligibility) puts_requested={puts_req} calls_requested={calls_req} "
        f"sample_symbols[0:3]={first_3} -> {'PASS' if mode_integrity_pass else 'FAIL'}"
    )
    analysis_lines.append("\n## Mode Integrity\n\n" + mode_integrity_line + "\n")
    print("\n--- Mode Integrity ---")
    if mode_integrity_pass:
        print("Mode Integrity: PASS")
    else:
        print(mode_integrity_line)
        if mode_integrity_fail_reason:
            print(mode_integrity_fail_reason, file=sys.stderr)

    # Top Candidates Table (10 rows)
    top_candidates = trace.get("top_candidates_table") or trace.get("top_candidates") or []
    if not top_candidates and (opt.get("top_rejection_reasons") or {}).get("sample_rejected_candidates"):
        for r in (opt.get("top_rejection_reasons") or {}).get("sample_rejected_candidates", [])[:10]:
            top_candidates.append({
                "exp": r.get("exp"), "strike": r.get("strike"), "OTM?": r.get("OTM?"),
                "abs_delta": r.get("abs_delta"), "bid": r.get("bid"), "ask": r.get("ask"),
                "spread_pct": r.get("spread_pct"), "oi": r.get("oi"),
                "passes_required_fields?": r.get("passes_required_fields?"), "passes_delta_band?": r.get("passes_delta_band?"),
                "rejection_reason": r.get("rejection_reason", ""),
            })
    table_lines = ["## Top Candidates Table (10 rows)", ""]
    cols = ["exp", "strike", "OTM?", "abs_delta", "bid", "ask", "spread_pct", "oi", "passes_required_fields?", "passes_delta_band?", "rejection_reason"]
    table_lines.append("| " + " | ".join(cols) + " |")
    table_lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for row in (top_candidates or [])[:10]:
        table_lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
    if not top_candidates:
        table_lines.append("(no candidates in trace)")
    table_lines.append("")
    analysis_lines.extend(table_lines)
    print("\n--- Stage-2 Truth Summary ---")
    for line in truth_lines:
        print(line)
    print("\n--- Top Candidates Table ---")
    for line in table_lines:
        print(line)

    out_md = out_dir / f"{symbol}_analysis.md"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(analysis_lines))
    print(f"Wrote {out_md}")

    # --- Console summary ---
    print("\n--- Summary ---")
    snapshot_time = (data_snap or {}).get("snapshot_time") or (data_diag or {}).get("fetched_at") or "N/A"
    print(f"snapshot_time: {snapshot_time}")
    if snap_obj:
        print(f"price: {snap_obj.get('price')}")
        print(f"bid: {snap_obj.get('bid')}")
        print(f"ask: {snap_obj.get('ask')}")
        print(f"volume: {snap_obj.get('volume')}")
        print(f"quote_as_of / quote_date: {snap_obj.get('quote_as_of') or snap_obj.get('quote_date')}")
        print(f"iv_rank: {snap_obj.get('iv_rank')}")
    print(f"missing_reasons (required keys): {[k for k in REQUIRED_FIELDS if (missing_reasons or {}).get(k)] or []}")
    if missing_fields:
        print(f"BLOCK reason: required field(s) missing: {missing_fields}", file=sys.stderr)
    if is_stale and not missing_fields:
        print("BLOCK reason: quote_date stale (Stage-1)", file=sys.stderr)
    for r in block_reasons:
        print(f"  {r}", file=sys.stderr)

    # --- Exit code: request errors first ---
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    # Required field missing => exit 2
    if missing_fields:
        return 2
    # Stage-1 BLOCKED (e.g. stale) => exit 3
    if is_stale:
        return 3
    # Phase 3.2 acceptance checks (must be printed)
    if data_diag is not None:
        tel = (data_diag.get("options") or {}).get("strikes_options_telemetry") or {}
        trace = data_diag.get("stage2_trace")
        cd = data_diag.get("contract_data") or {}
        opt_counts = (data_diag.get("options") or {}).get("option_type_counts") or {}
        sample_syms = tel.get("sample_request_symbols") or (trace or {}).get("sample_request_symbols") or []
        req_strikes = tel.get("requested_put_strikes") or (trace or {}).get("requested_put_strikes")
        print("\n--- Phase 3.2 acceptance ---")
        print(f"  sample_request_symbols[0:3]= {sample_syms[:3]}")
        print(f"  calls_seen= {opt_counts.get('calls_seen', 'N/A')}")
        print(f"  otm_puts_in_delta_band= {cd.get('otm_puts_in_delta_band', 'N/A')}")
        print(f"  stage2_trace non-null= {trace is not None and isinstance(trace, dict)}")
        is_fallback = (trace or {}).get("message") == "Minimal trace (validate_one_symbol fallback)"
        print(f"  stage2_trace.json is real (not fallback)= {not is_fallback}")
        if req_strikes:
            print(f"  requested_put_strikes= {req_strikes}")

    # Phase 3.8: Mode integrity FAIL => exit 6 (reason already printed to stderr in Mode Integrity section)
    if not mode_integrity_pass:
        return 6

    # Phase 3.3.1: eligibility and contract checks (symbol_eligibility, contract_data, contract_eligibility)
    if data_diag is not None:
        exit_ec, msg_list = _eligibility_and_contract_assert(data_diag)
        if exit_ec is not None:
            for m in msg_list:
                print(m, file=sys.stderr)
            return exit_ec
        for m in msg_list:
            print(m, file=sys.stderr)  # WARN messages (e.g. required_fields_present False)
        # When chain available but no contract passed (FAIL), that's informational, not an error
        cd = data_diag.get("contract_data") or {}
        ce = data_diag.get("contract_eligibility") or {}
        if cd.get("available") is True and (ce or {}).get("status") == "FAIL":
            print("INFO: Chain available but no contracts passed filters.")
            print(f"  Reasons: {ce.get('reasons', [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
