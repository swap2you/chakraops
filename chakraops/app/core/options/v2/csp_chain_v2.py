# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Stage-2 CSP V2 — PUT-only, OTM-only. Liquidity gates enforced before selection.
Output: full stage2_trace dict (shared contract).
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.core.orats.endpoints import BASE_DATAV2, PATH_STRIKES, PATH_STRIKES_OPTIONS
from app.core.orats.orats_opra import build_orats_option_symbol
from app.core.config.wheel_strategy_config import (
    MIN_OTM_STRIKE_PCT_CSP,
    STRIKES_PER_EXPIRY_CSP,
    DELTA_BAND_MIN,
    DELTA_BAND_MAX,
    MIN_OPEN_INTEREST,
    MAX_SPREAD_PCT,
)
from app.core.config.wheel_strategy_config import get_dte_range
from app.core.options.orats_chain_pipeline import _delta_to_decimal

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("strike", "exp", "delta", "bid", "ask")
TIMEOUT_SEC = 15
OPRA_BATCH_SIZE = 10


def _get_orats_token() -> str:
    from app.core.config.orats_secrets import ORATS_API_TOKEN
    return ORATS_API_TOKEN


def _get_strikes_options_param_name() -> str:
    return "tickers"


def _safe_oi(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


@dataclass
class Stage2V2Result:
    """V2 engine result. stage2_trace is always full."""
    success: bool
    error_code: Optional[str] = None
    spot_used: Optional[float] = None
    available: bool = False
    selected_trade: Optional[Dict[str, Any]] = None
    top_rejection: Optional[str] = None
    top_rejection_reason: Optional[str] = None  # backward compat
    sample_rejections: List[Dict[str, Any]] = field(default_factory=list)
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)
    stage2_trace: Dict[str, Any] = field(default_factory=dict)
    contract_count: int = 0


def run_csp_stage2_v2(
    symbol: str,
    spot_used: float,
    snapshot_time: Optional[str] = None,
    quote_as_of: Optional[str] = None,
    dte_min: Optional[int] = None,
    dte_max: Optional[int] = None,
    max_expiries: int = 5,
    min_otm_pct: Optional[float] = None,
    strikes_per_expiry: Optional[int] = None,
    delta_lo: Optional[float] = None,
    delta_hi: Optional[float] = None,
    min_open_interest: Optional[int] = None,
    max_spread_pct: Optional[float] = None,
) -> Stage2V2Result:
    """
    CSP V2: PUT-only, OTM-only. Liquidity gates (MIN_OI, MAX_SPREAD_PCT) enforced before selection.
    """
    dte_min = dte_min if dte_min is not None else get_dte_range()[0]
    dte_max = dte_max if dte_max is not None else get_dte_range()[1]
    min_otm_pct = min_otm_pct if min_otm_pct is not None else MIN_OTM_STRIKE_PCT_CSP
    strikes_per_expiry = strikes_per_expiry if strikes_per_expiry is not None else STRIKES_PER_EXPIRY_CSP
    delta_lo = delta_lo if delta_lo is not None else DELTA_BAND_MIN
    delta_hi = delta_hi if delta_hi is not None else DELTA_BAND_MAX
    min_open_interest = min_open_interest if min_open_interest is not None else MIN_OPEN_INTEREST
    max_spread_pct = max_spread_pct if max_spread_pct is not None else MAX_SPREAD_PCT

    symbol = symbol.upper().strip()
    trace: Dict[str, Any] = {"mode": "CSP"}
    trace["spot_used"] = spot_used
    trace["snapshot_time"] = snapshot_time
    trace["quote_as_of"] = quote_as_of
    trace["dte_window"] = [dte_min, dte_max]

    try:
        token = _get_orats_token()
    except Exception as e:
        return _fail("ORATS token unavailable", trace, str(e))
    url = f"{BASE_DATAV2.rstrip('/')}{PATH_STRIKES}"
    params = {"token": token, "ticker": symbol, "dte": f"{dte_min},{dte_max}"}
    t0 = time.perf_counter()
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        return _fail("Strikes request failed", trace, str(e))
    if r.status_code != 200:
        return _fail(f"Strikes HTTP {r.status_code}", trace, r.text[:200])
    try:
        raw = r.json()
    except ValueError as e:
        return _fail("Strikes invalid JSON", trace, str(e))
    rows = raw if isinstance(raw, list) else (raw.get("data", []) if isinstance(raw, dict) else [])
    trace["base_strikes_rows_total"] = len(rows)
    if not rows:
        return _fail("No strikes data returned", trace)

    expiry_rows: Dict[date, List[Dict]] = {}
    for row in rows:
        exp_str = row.get("expirDate")
        if not exp_str:
            continue
        try:
            exp_date = datetime.strptime(exp_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if exp_date not in expiry_rows:
            expiry_rows[exp_date] = []
        expiry_rows[exp_date].append(row)
    sorted_expiries = sorted(expiry_rows.keys())[:max_expiries]
    if not sorted_expiries:
        return _fail("NO_EXPIRATIONS_IN_DTE", trace)
    trace["expirations_in_window"] = [e.isoformat() for e in sorted_expiries]
    trace["expirations_count"] = len(sorted_expiries)

    # S3: OTM put strikes
    selected_per_expiry: Dict[date, List[float]] = {}
    for exp in sorted_expiries:
        rows_exp = expiry_rows[exp]
        strikes_all = sorted(set(float(r.get("strike", 0)) for r in rows_exp if r.get("strike") is not None))
        otm = [s for s in strikes_all if s < spot_used]
        if not otm:
            continue
        min_floor = spot_used * min_otm_pct
        near_otm = [s for s in otm if s >= min_floor]
        if not near_otm:
            return _fail("CSP_NO_OTM_STRIKES_NEAR_SPOT", trace, f"spot={spot_used} min_pct={min_otm_pct}")
        selected = sorted(near_otm)[-strikes_per_expiry:]
        selected_per_expiry[exp] = selected
    if not selected_per_expiry:
        return _fail("CSP_NO_OTM_STRIKES_NEAR_SPOT", trace, f"spot={spot_used} min_pct={min_otm_pct}")

    # S4: Build OCC symbols (PUT only)
    option_symbols: List[str] = []
    for exp, strikes in selected_per_expiry.items():
        exp_str = exp.strftime("%Y-%m-%d")
        for strike in strikes:
            if strike >= spot_used:
                return _fail("CSP_REQUEST_INCLUDED_ITM", trace, f"strike={strike} spot={spot_used}")
            option_symbols.append(build_orats_option_symbol(symbol, exp_str, "P", strike))
    puts_requested = len(option_symbols)
    trace["request_counts"] = {"puts_requested": puts_requested, "calls_requested": 0}
    trace["sample_request_symbols"] = option_symbols[:10]
    if not option_symbols:
        return _fail("CSP_NO_OTM_STRIKES_NEAR_SPOT", trace)

    # S5: Enrichment
    param_name = _get_strikes_options_param_name()
    options_url = f"{BASE_DATAV2.rstrip('/')}{PATH_STRIKES_OPTIONS}"
    enrichment_rows: List[Dict[str, Any]] = []
    for i in range(0, len(option_symbols), OPRA_BATCH_SIZE):
        batch = option_symbols[i : i + OPRA_BATCH_SIZE]
        try:
            r2 = requests.get(options_url, params={"token": token, param_name: ",".join(batch)}, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            logger.warning("[CSP_V2] options request failed: %s", e)
            continue
        if r2.status_code != 200:
            continue
        try:
            raw2 = r2.json()
        except ValueError:
            continue
        rows2 = raw2 if isinstance(raw2, list) else (raw2.get("data", []) if isinstance(raw2, dict) else [])
        for row in rows2:
            put_call = (row.get("putCall") or row.get("optionType") or "").strip().upper()
            if put_call in ("C", "CALL"):
                return _fail("CSP_REQUEST_BUILT_CALLS", trace, "CALL in response")
            enrichment_rows.append(row)
    trace["response_rows"] = len(enrichment_rows)
    trace["available"] = len(enrichment_rows) > 0

    # S6: Candidate mapping
    _debug_delta_samples: List[Tuple[Any, float, float]] = []
    candidates: List[Dict[str, Any]] = []
    missing_counts: Dict[str, int] = {f: 0 for f in REQUIRED_FIELDS}
    for row in enrichment_rows:
        option_symbol = (row.get("optionSymbol") or "").replace(" ", "").strip()
        if not option_symbol or len(option_symbol) < 16:
            continue
        put_call = (row.get("putCall") or row.get("optionType") or "").strip().upper()
        if put_call in ("C", "CALL"):
            return _fail("CSP_REQUEST_BUILT_CALLS", trace, f"sym={option_symbol}")
        bid = row.get("bidPrice") or row.get("bid")
        ask = row.get("askPrice") or row.get("ask")
        strike_raw = row.get("strike")
        exp_raw = row.get("expirDate") or row.get("expiration")
        delta_raw = row.get("delta")
        oi_raw = row.get("openInt") or row.get("openInterest") or row.get("open_interest") or row.get("oi")
        try:
            strike = float(strike_raw) if strike_raw is not None else None
        except (TypeError, ValueError):
            strike = None
        delta_decimal = _delta_to_decimal(delta_raw) if delta_raw is not None else None
        if os.environ.get("CHAKRAOPS_DEBUG_DELTA") == "1" and delta_raw is not None and delta_decimal is not None and len(_debug_delta_samples) < 3:
            _debug_delta_samples.append((delta_raw, delta_decimal, abs(delta_decimal)))
        c = {
            "optionSymbol": option_symbol,
            "putCall": "P",
            "strike": strike,
            "exp": exp_raw,
            "delta": delta_decimal,
            "bid": float(bid) if bid is not None and not isinstance(bid, str) else None,
            "ask": float(ask) if ask is not None and not isinstance(ask, str) else None,
            "open_interest": _safe_oi(oi_raw),
        }
        for fn in REQUIRED_FIELDS:
            val = c.get(fn)
            if val is None or (isinstance(val, float) and math.isnan(val)):
                missing_counts[fn] = missing_counts.get(fn, 0) + 1
        candidates.append(c)
    puts_with_required = sum(1 for c in candidates if all(c.get(f) is not None for f in REQUIRED_FIELDS))
    trace["puts_with_required_fields"] = puts_with_required
    trace["calls_with_required_fields"] = 0
    trace["missing_required_fields_counts"] = dict(missing_counts)

    # S7: Filter + selection (with liquidity gates)
    spot = spot_used
    otm_puts = [c for c in candidates if c.get("strike") is not None and c["strike"] < spot]
    trace["otm_contracts_in_dte"] = len(otm_puts)
    trace["otm_puts_in_dte"] = len(otm_puts)  # backward compat
    abs_deltas = [abs(float(c["delta"])) for c in otm_puts if c.get("delta") is not None]
    trace["delta_abs_stats"] = (
        {"min": round(min(abs_deltas), 4), "median": round(sorted(abs_deltas)[len(abs_deltas) // 2], 4), "max": round(max(abs_deltas), 4)}
        if abs_deltas else {"min": None, "median": None, "max": None}
    )
    in_delta_band = [
        c for c in otm_puts
        if c.get("delta") is not None and delta_lo <= abs(float(c["delta"])) <= delta_hi
    ]
    trace["otm_contracts_in_delta_band"] = len(in_delta_band)
    trace["otm_puts_in_delta_band"] = len(in_delta_band)  # backward compat

    if os.environ.get("CHAKRAOPS_DEBUG_DELTA") == "1":
        min_abs = round(min(abs_deltas), 4) if abs_deltas else None
        max_abs = round(max(abs_deltas), 4) if abs_deltas else None
        logger.info(
            "[DEBUG_DELTA] symbol=%s strategy=CSP quote_date=%s target_band=(%.2f,%.2f) count_total=%d count_in_band=%d min_abs_delta_dec=%s max_abs_delta_dec=%s samples=%s",
            symbol, trace.get("quote_as_of") or trace.get("snapshot_time") or "—",
            delta_lo, delta_hi, len(otm_puts), len(in_delta_band), min_abs, max_abs, _debug_delta_samples[:3],
        )

    def _spread_pct(c: Dict) -> Optional[float]:
        b, a = c.get("bid"), c.get("ask")
        if b is None or a is None:
            return None
        mid = (b + a) / 2
        return (a - b) / mid if mid else None

    # Liquidity gates: OI >= min_open_interest, spread_pct <= max_spread_pct
    passed_liquidity: List[Dict[str, Any]] = []
    rejected_counts: Dict[str, int] = {
        "rejected_due_to_wrong_type": 0,
        "rejected_due_to_itm": 0,
        "rejected_due_to_missing_fields": 0,
        "rejected_due_to_delta": 0,
        "rejected_due_to_oi": 0,
        "rejected_due_to_spread": 0,
    }
    first_delta_rejection_sample: List[Dict[str, Any]] = []  # ensure at least one when count > 0
    for c in otm_puts:
        passes_req = all(c.get(f) is not None for f in REQUIRED_FIELDS)
        d_raw = c.get("delta")
        delta_abs = abs(float(d_raw)) if d_raw is not None else None
        passes_delta = delta_abs is not None and delta_lo <= delta_abs <= delta_hi
        oi = c.get("open_interest")
        passes_oi = oi is not None and oi >= min_open_interest
        sp = _spread_pct(c)
        passes_spread = sp is not None and sp <= max_spread_pct
        if passes_req and passes_delta and passes_oi and passes_spread:
            passed_liquidity.append(c)
        else:
            if not passes_req:
                rejected_counts["rejected_due_to_missing_fields"] += 1
            elif not passes_delta:
                rejected_counts["rejected_due_to_delta"] += 1
                if not first_delta_rejection_sample and d_raw is not None:
                    first_delta_rejection_sample.append({
                        "observed_delta_decimal_raw": round(float(d_raw), 4),
                        "observed_delta_decimal_abs": round(delta_abs, 4) if delta_abs is not None else None,
                        "observed_delta_pct_abs": round(delta_abs * 100, 1) if delta_abs is not None else None,
                        "target_range_decimal": f"{delta_lo}-{delta_hi}",
                    })
            elif not passes_oi:
                rejected_counts["rejected_due_to_oi"] += 1
            elif not passes_spread:
                rejected_counts["rejected_due_to_spread"] += 1

    table_rows: List[Dict[str, Any]] = []
    sample_rejections: List[Dict[str, Any]] = []
    sample_rejected_due_to_delta: List[Dict[str, Any]] = []
    for c in otm_puts[:20]:
        passes_req = all(c.get(f) is not None for f in REQUIRED_FIELDS)
        d_raw = c.get("delta")
        d_abs = abs(float(d_raw)) if d_raw is not None else None
        passes_delta = d_abs is not None and delta_lo <= d_abs <= delta_hi
        oi = c.get("open_interest")
        passes_oi = oi is not None and oi >= min_open_interest
        sp = _spread_pct(c)
        passes_spread = sp is not None and sp <= max_spread_pct
        if not passes_req:
            rej = "missing_required_fields"
        elif not passes_delta:
            rej = "delta_out_of_band"
            if len(sample_rejected_due_to_delta) < 3 and d_raw is not None:
                sample_rejected_due_to_delta.append({
                    "observed_delta_decimal_raw": round(float(d_raw), 4),
                    "observed_delta_decimal_abs": round(d_abs, 4) if d_abs is not None else None,
                    "observed_delta_pct_abs": round(d_abs * 100, 1) if d_abs is not None else None,
                    "target_range_decimal": f"{delta_lo}-{delta_hi}",
                })
        elif not passes_oi:
            rej = "oi_below_min"
        elif not passes_spread:
            rej = "spread_too_wide"
        else:
            rej = ""
        row = {
            "exp": c.get("exp"), "strike": c.get("strike"),
            "OTM?": c.get("strike") is not None and c["strike"] < spot,
            "abs_delta": round(d_abs, 4) if d_abs is not None else None,
            "bid": c.get("bid"), "ask": c.get("ask"),
            "spread_pct": round(sp, 4) if sp is not None else None,
            "oi": oi,
            "passes_required_fields?": passes_req,
            "passes_delta_band?": passes_delta,
            "rejection_reason": rej,
        }
        table_rows.append(row)
        if rej and len(sample_rejections) < 10:
            sample_rejections.append(row)
    trace["rejection_counts"] = rejected_counts
    # When rejected_due_to_delta > 0, always expose at least one sample (from first failing contract)
    trace["sample_rejected_due_to_delta"] = first_delta_rejection_sample if first_delta_rejection_sample else sample_rejected_due_to_delta
    trace["rejected_counts"] = rejected_counts  # backward compat
    trace["sample_rejections"] = sample_rejections[:10]
    trace["top_candidates_table"] = table_rows[:10]

    # Select best: max bid, tie-break delta near 0.30, then lowest spread
    selected_trade: Optional[Dict[str, Any]] = None
    top_rejection: Optional[str] = None
    if passed_liquidity:
        def sel_key(c: Dict) -> Tuple[float, float, float]:
            bid = c.get("bid") or 0
            da = abs(float(c.get("delta") or 0))
            d_dist = abs(da - 0.30)
            sp = _spread_pct(c) or 1.0
            return (bid, -d_dist, -sp)
        passed_liquidity.sort(key=sel_key, reverse=True)
        best = passed_liquidity[0]
        bid = best.get("bid")
        ask = best.get("ask")
        sp = _spread_pct(best)
        selected_trade = {
            "symbol": symbol,
            "exp": best.get("exp"),
            "strike": best.get("strike"),
            "abs_delta": round(abs(float(best.get("delta") or 0)), 4),
            "bid": bid,
            "ask": ask,
            "credit_estimate": bid,
            "spread_pct": round(sp, 4) if sp is not None else None,
            "oi": best.get("open_interest"),
        }
        trace["stage2_status"] = "PASS"
        trace["error_code"] = None
    else:
        top_key = max(rejected_counts, key=rejected_counts.get)
        top_rejection = f"{top_key}={rejected_counts.get(top_key, 0)}"
        trace["stage2_status"] = "FAIL"
        trace["error_code"] = None
    trace["top_rejection"] = top_rejection
    trace["top_rejection_reason"] = top_rejection  # backward compat
    trace["selected_trade"] = selected_trade

    return Stage2V2Result(
        success=selected_trade is not None,
        error_code=None if selected_trade else (trace.get("error") or top_rejection),
        spot_used=spot_used,
        available=len(enrichment_rows) > 0,
        selected_trade=selected_trade,
        top_rejection=top_rejection,
        top_rejection_reason=top_rejection,  # backward compat
        sample_rejections=sample_rejections[:10],
        top_candidates=table_rows[:10],
        stage2_trace=trace,
        contract_count=len(candidates),
    )


def _fail(error: str, trace: Dict[str, Any], message: Optional[str] = None) -> Stage2V2Result:
    trace["mode"] = trace.get("mode", "CSP")
    trace["stage2_status"] = "ERROR"
    trace["error_code"] = error
    trace["selected_trade"] = None
    trace["top_rejection"] = None
    trace.setdefault("expirations_in_window", [])
    trace.setdefault("request_counts", {"puts_requested": 0, "calls_requested": 0})
    trace.setdefault("response_rows", 0)
    trace.setdefault("puts_with_required_fields", 0)
    trace.setdefault("calls_with_required_fields", 0)
    trace.setdefault("otm_contracts_in_dte", 0)
    trace.setdefault("otm_contracts_in_delta_band", 0)
    trace.setdefault("otm_puts_in_dte", 0)
    trace.setdefault("otm_puts_in_delta_band", 0)
    trace.setdefault("delta_abs_stats", {"min": None, "median": None, "max": None})
    trace.setdefault("rejection_counts", {})
    trace.setdefault("top_candidates_table", [])
    trace.setdefault("sample_request_symbols", [])
    if message:
        trace["message"] = message
    return Stage2V2Result(success=False, error_code=error, spot_used=trace.get("spot_used"), available=False, stage2_trace=trace, contract_count=0)
