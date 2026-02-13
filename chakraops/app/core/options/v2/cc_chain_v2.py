# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Stage-2 CC V2 — CALL-only, OTM-only (strike > spot). Liquidity gates enforced before selection.
Output: full stage2_trace dict (shared contract).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.core.orats.endpoints import BASE_DATAV2, PATH_STRIKES, PATH_STRIKES_OPTIONS
from app.core.orats.orats_opra import build_orats_option_symbol
from app.core.config.wheel_strategy_config import (
    MAX_OTM_STRIKE_PCT_CC,
    STRIKES_PER_EXPIRY_CC,
    DELTA_BAND_MIN,
    DELTA_BAND_MAX,
    MIN_OPEN_INTEREST,
    MAX_SPREAD_PCT,
)
from app.core.config.wheel_strategy_config import get_dte_range

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
    top_rejection_reason: Optional[str] = None
    sample_rejections: List[Dict[str, Any]] = field(default_factory=list)
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)
    stage2_trace: Dict[str, Any] = field(default_factory=dict)
    contract_count: int = 0


def run_cc_stage2_v2(
    symbol: str,
    spot_used: float,
    snapshot_time: Optional[str] = None,
    quote_as_of: Optional[str] = None,
    dte_min: Optional[int] = None,
    dte_max: Optional[int] = None,
    max_expiries: int = 5,
    max_otm_pct: Optional[float] = None,
    strikes_per_expiry: Optional[int] = None,
    delta_lo: Optional[float] = None,
    delta_hi: Optional[float] = None,
    min_open_interest: Optional[int] = None,
    max_spread_pct: Optional[float] = None,
) -> Stage2V2Result:
    """
    CC V2: CALL-only, OTM-only (strike > spot). Liquidity gates enforced before selection.
    """
    dte_min = dte_min if dte_min is not None else get_dte_range()[0]
    dte_max = dte_max if dte_max is not None else get_dte_range()[1]
    max_otm_pct = max_otm_pct if max_otm_pct is not None else MAX_OTM_STRIKE_PCT_CC
    strikes_per_expiry = strikes_per_expiry if strikes_per_expiry is not None else STRIKES_PER_EXPIRY_CC
    delta_lo = delta_lo if delta_lo is not None else DELTA_BAND_MIN
    delta_hi = delta_hi if delta_hi is not None else DELTA_BAND_MAX
    min_open_interest = min_open_interest if min_open_interest is not None else MIN_OPEN_INTEREST
    max_spread_pct = max_spread_pct if max_spread_pct is not None else MAX_SPREAD_PCT

    symbol = symbol.upper().strip()
    trace: Dict[str, Any] = {"mode": "CC"}
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

    # OTM call strikes: strike > spot_used
    selected_per_expiry: Dict[date, List[float]] = {}
    for exp in sorted_expiries:
        rows_exp = expiry_rows[exp]
        strikes_all = sorted(set(float(r.get("strike", 0)) for r in rows_exp if r.get("strike") is not None))
        otm_calls = [s for s in strikes_all if s > spot_used]
        if not otm_calls:
            continue
        max_ceiling = spot_used * max_otm_pct
        near_otm = [s for s in otm_calls if s <= max_ceiling]
        if not near_otm:
            return _fail("CC_NO_OTM_STRIKES_NEAR_SPOT", trace, f"spot={spot_used} max_pct={max_otm_pct}")
        selected = sorted(near_otm)[:strikes_per_expiry]
        selected_per_expiry[exp] = selected
    if not selected_per_expiry:
        return _fail("CC_NO_OTM_STRIKES_NEAR_SPOT", trace, f"spot={spot_used} max_pct={max_otm_pct}")

    # Build OCC symbols (CALL only)
    option_symbols: List[str] = []
    for exp, strikes in selected_per_expiry.items():
        exp_str = exp.strftime("%Y-%m-%d")
        for strike in strikes:
            if strike <= spot_used:
                return _fail("CC_REQUEST_INCLUDED_ITM", trace, f"strike={strike} spot={spot_used}")
            option_symbols.append(build_orats_option_symbol(symbol, exp_str, "C", strike))
    calls_requested = len(option_symbols)
    trace["request_counts"] = {"puts_requested": 0, "calls_requested": calls_requested}
    trace["sample_request_symbols"] = option_symbols[:10]
    if not option_symbols:
        return _fail("CC_NO_OTM_STRIKES_NEAR_SPOT", trace)

    # Enrichment
    param_name = _get_strikes_options_param_name()
    options_url = f"{BASE_DATAV2.rstrip('/')}{PATH_STRIKES_OPTIONS}"
    enrichment_rows: List[Dict[str, Any]] = []
    for i in range(0, len(option_symbols), OPRA_BATCH_SIZE):
        batch = option_symbols[i : i + OPRA_BATCH_SIZE]
        try:
            r2 = requests.get(options_url, params={"token": token, param_name: ",".join(batch)}, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            logger.warning("[CC_V2] options request failed: %s", e)
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
            if put_call in ("P", "PUT"):
                return _fail("CC_REQUEST_BUILT_PUTS", trace, "PUT in response")
            enrichment_rows.append(row)
    trace["response_rows"] = len(enrichment_rows)
    trace["available"] = len(enrichment_rows) > 0

    # Candidate mapping
    candidates: List[Dict[str, Any]] = []
    missing_counts: Dict[str, int] = {f: 0 for f in REQUIRED_FIELDS}
    for row in enrichment_rows:
        option_symbol = (row.get("optionSymbol") or "").replace(" ", "").strip()
        if not option_symbol or len(option_symbol) < 16:
            continue
        put_call = (row.get("putCall") or row.get("optionType") or "").strip().upper()
        if put_call in ("P", "PUT"):
            return _fail("CC_REQUEST_BUILT_PUTS", trace, f"sym={option_symbol}")
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
        c = {
            "optionSymbol": option_symbol,
            "putCall": "C",
            "strike": strike,
            "exp": exp_raw,
            "delta": float(delta_raw) if delta_raw is not None and not isinstance(delta_raw, str) else None,
            "bid": float(bid) if bid is not None and not isinstance(bid, str) else None,
            "ask": float(ask) if ask is not None and not isinstance(ask, str) else None,
            "open_interest": _safe_oi(oi_raw),
        }
        for fn in REQUIRED_FIELDS:
            val = c.get(fn)
            if val is None or (isinstance(val, float) and math.isnan(val)):
                missing_counts[fn] = missing_counts.get(fn, 0) + 1
        candidates.append(c)
    calls_with_required = sum(1 for c in candidates if all(c.get(f) is not None for f in REQUIRED_FIELDS))
    trace["puts_with_required_fields"] = 0
    trace["calls_with_required_fields"] = calls_with_required
    trace["missing_required_fields_counts"] = dict(missing_counts)

    # Filter + selection (OTM calls: strike > spot)
    spot = spot_used
    otm_calls = [c for c in candidates if c.get("strike") is not None and c["strike"] > spot]
    trace["otm_contracts_in_dte"] = len(otm_calls)
    trace["otm_calls_in_dte"] = len(otm_calls)
    abs_deltas = [abs(float(c["delta"])) for c in otm_calls if c.get("delta") is not None]
    trace["delta_abs_stats"] = (
        {"min": round(min(abs_deltas), 4), "median": round(sorted(abs_deltas)[len(abs_deltas) // 2], 4), "max": round(max(abs_deltas), 4)}
        if abs_deltas else {"min": None, "median": None, "max": None}
    )
    in_delta_band = [
        c for c in otm_calls
        if c.get("delta") is not None and delta_lo <= abs(float(c["delta"])) <= delta_hi
    ]
    trace["otm_contracts_in_delta_band"] = len(in_delta_band)
    trace["otm_calls_in_delta_band"] = len(in_delta_band)

    def _spread_pct(c: Dict) -> Optional[float]:
        b, a = c.get("bid"), c.get("ask")
        if b is None or a is None:
            return None
        mid = (b + a) / 2
        return (a - b) / mid if mid else None

    passed_liquidity: List[Dict[str, Any]] = []
    rejected_counts: Dict[str, int] = {
        "rejected_due_to_wrong_type": 0,
        "rejected_due_to_itm": 0,
        "rejected_due_to_missing_fields": 0,
        "rejected_due_to_delta": 0,
        "rejected_due_to_oi": 0,
        "rejected_due_to_spread": 0,
    }
    for c in otm_calls:
        passes_req = all(c.get(f) is not None for f in REQUIRED_FIELDS)
        delta_abs = abs(float(c["delta"])) if c.get("delta") is not None else None
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
            elif not passes_oi:
                rejected_counts["rejected_due_to_oi"] += 1
            elif not passes_spread:
                rejected_counts["rejected_due_to_spread"] += 1

    table_rows: List[Dict[str, Any]] = []
    sample_rejections: List[Dict[str, Any]] = []
    for c in otm_calls[:20]:
        passes_req = all(c.get(f) is not None for f in REQUIRED_FIELDS)
        delta_abs = abs(float(c["delta"])) if c.get("delta") is not None else None
        passes_delta = delta_abs is not None and delta_lo <= delta_abs <= delta_hi
        oi = c.get("open_interest")
        passes_oi = oi is not None and oi >= min_open_interest
        sp = _spread_pct(c)
        passes_spread = sp is not None and sp <= max_spread_pct
        if not passes_req:
            rej = "missing_required_fields"
        elif not passes_delta:
            rej = "delta_out_of_band"
        elif not passes_oi:
            rej = "oi_below_min"
        elif not passes_spread:
            rej = "spread_too_wide"
        else:
            rej = ""
        row = {
            "exp": c.get("exp"), "strike": c.get("strike"),
            "OTM?": c.get("strike") is not None and c["strike"] > spot,
            "abs_delta": round(delta_abs, 4) if delta_abs is not None else None,
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
    trace["rejected_counts"] = rejected_counts
    trace["sample_rejections"] = sample_rejections[:10]
    trace["top_candidates_table"] = table_rows[:10]

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
    trace["top_rejection_reason"] = top_rejection
    trace["selected_trade"] = selected_trade

    return Stage2V2Result(
        success=selected_trade is not None,
        error_code=None if selected_trade else (trace.get("error") or top_rejection),
        spot_used=spot_used,
        available=len(enrichment_rows) > 0,
        selected_trade=selected_trade,
        top_rejection=top_rejection,
        top_rejection_reason=top_rejection,
        sample_rejections=sample_rejections[:10],
        top_candidates=table_rows[:10],
        stage2_trace=trace,
        contract_count=len(candidates),
    )


def _fail(error: str, trace: Dict[str, Any], message: Optional[str] = None) -> Stage2V2Result:
    trace["mode"] = trace.get("mode", "CC")
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
    trace.setdefault("otm_calls_in_dte", 0)
    trace.setdefault("otm_calls_in_delta_band", 0)
    trace.setdefault("delta_abs_stats", {"min": None, "median": None, "max": None})
    trace.setdefault("rejection_counts", {})
    trace.setdefault("top_candidates_table", [])
    trace.setdefault("sample_request_symbols", [])
    if message:
        trace["message"] = message
    return Stage2V2Result(success=False, error_code=error, spot_used=trace.get("spot_used"), available=False, stage2_trace=trace, contract_count=0)
