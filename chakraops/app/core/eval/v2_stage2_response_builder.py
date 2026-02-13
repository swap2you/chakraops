# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 3.8: Canonical Stage-2 response builder (V2 only).
Single writer for selected_trade, top_rejection, rejection_counts, and mode-correct schema.
DO NOT modify V2 selection logic; only map outputs consistently.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Canonical top-level keys (required)
REQUIRED_KEYS = (
    "strategy_mode",
    "stage2_ran",
    "chain_available",
    "expirations_in_window",
    "request_counts",
    "response_rows",
    "required_fields_present",
    "contracts_in_delta_band",
    "selected_trade",
    "top_rejection",
    "rejection_counts",
    "samples",
)

MODE_CSP = "CSP"
MODE_CC = "CC"
ERROR_MODE_MIXED_CC = "MODE_MIXED_CONTRACTS_CC"
ERROR_MODE_MIXED_CSP = "MODE_MIXED_CONTRACTS_CSP"


def run_mode_guardrails(strategy_mode: str, trace: Dict[str, Any]) -> Optional[str]:
    """
    Fail-fast: if mode and request symbols/counts contradict, return error code.
    - CC must have puts_requested==0 and no "P" in request symbols.
    - CSP must have calls_requested==0 and no "C" in request symbols.
    """
    if not isinstance(trace, dict):
        return None
    mode = (strategy_mode or "").strip().upper() or MODE_CSP
    req = trace.get("request_counts") or {}
    puts_req = req.get("puts_requested", 0) or 0
    calls_req = req.get("calls_requested", 0) or 0
    symbols = trace.get("sample_request_symbols") or []

    # OCC option symbol: ROOT + YYMMDD(6) + C|P(1) + 8-digit strike -> C/P at index -9 from end
    if mode == MODE_CC:
        if puts_req > 0:
            return ERROR_MODE_MIXED_CC
        for s in (symbols or [])[:20]:
            if not isinstance(s, str) or len(s) < 12:
                continue
            clean = s.replace(" ", "").upper()
            if len(clean) >= 17 and clean[-9] == "P":
                return ERROR_MODE_MIXED_CC
    elif mode == MODE_CSP:
        if calls_req > 0:
            return ERROR_MODE_MIXED_CSP
        for s in (symbols or [])[:20]:
            if not isinstance(s, str) or len(s) < 12:
                continue
            clean = s.replace(" ", "").upper()
            if len(clean) >= 17 and clean[-9] == "C":
                return ERROR_MODE_MIXED_CSP
    return None


def build_canonical_payload(
    strategy_mode: str,
    stage2_trace: Optional[Dict[str, Any]],
    fetched_at_iso: Optional[str],
) -> Dict[str, Any]:
    """
    Build canonical Stage-2 payload from V2 trace only.
    Single source of truth; mode-correct (no put-named fields in CC, no call-named in CSP).
    """
    mode = (strategy_mode or "").strip().upper() or MODE_CSP
    trace = stage2_trace if isinstance(stage2_trace, dict) else {}

    err = run_mode_guardrails(mode, trace)
    if err:
        return {
            "strategy_mode": mode,
            "stage2_ran": True,
            "chain_available": False,
            "expirations_in_window": trace.get("expirations_in_window") or [],
            "request_counts": trace.get("request_counts") or {"puts_requested": 0, "calls_requested": 0},
            "response_rows": trace.get("response_rows") or 0,
            "required_fields_present": False,
            "contracts_in_delta_band": 0,
            "selected_trade": None,
            "top_rejection": err,
            "rejection_counts": {},
            "samples": {
                "sample_request_symbols": trace.get("sample_request_symbols") or [],
                "top_candidates_table": trace.get("top_candidates_table") or [],
            },
            "error_code": err,
            **(_mode_specific_counts(mode, trace, error=True)),
        }

    stage2_ran = bool(trace.get("response_rows") is not None)
    chain_available = (trace.get("response_rows") or 0) > 0
    req_counts = trace.get("request_counts") or {}
    puts_req = req_counts.get("puts_requested", 0) or 0
    calls_req = req_counts.get("calls_requested", 0) or 0
    response_rows = trace.get("response_rows") or 0
    required_fields_present = (trace.get("puts_with_required_fields") or 0) > 0 or (trace.get("calls_with_required_fields") or 0) > 0
    contracts_in_delta_band = (
        trace.get("otm_contracts_in_delta_band")
        or trace.get("otm_puts_in_delta_band")
        or trace.get("otm_calls_in_delta_band")
        or 0
    )
    selected_trade = trace.get("selected_trade")
    top_rejection = trace.get("top_rejection") or trace.get("top_rejection_reason")
    rejection_counts = dict(trace.get("rejection_counts") or trace.get("rejected_counts") or {})

    mode_counts = _mode_specific_counts(mode, trace, error=False)

    payload = {
        "strategy_mode": mode,
        "stage2_ran": stage2_ran,
        "chain_available": chain_available,
        "expirations_in_window": list(trace.get("expirations_in_window") or []),
        "request_counts": {"puts_requested": puts_req, "calls_requested": calls_req},
        "response_rows": response_rows,
        "required_fields_present": required_fields_present,
        "contracts_in_delta_band": contracts_in_delta_band,
        "selected_trade": selected_trade,
        "top_rejection": top_rejection,
        "rejection_counts": rejection_counts,
        "samples": {
            "sample_request_symbols": list(trace.get("sample_request_symbols") or [])[:10],
            "top_candidates_table": list(trace.get("top_candidates_table") or trace.get("top_candidates") or [])[:10],
        },
        "spot_used": trace.get("spot_used"),
        "as_of": fetched_at_iso,
        **mode_counts,
    }
    return payload


def _mode_specific_counts(mode: str, trace: Dict[str, Any], error: bool) -> Dict[str, Any]:
    """CSP: otm_puts_* only. CC: otm_calls_* only. Never cross."""
    if mode == MODE_CC:
        return {
            "otm_calls_in_dte": 0 if error else (trace.get("otm_calls_in_dte") or trace.get("otm_contracts_in_dte") or 0),
            "otm_calls_in_delta_band": 0 if error else (trace.get("otm_calls_in_delta_band") or trace.get("otm_contracts_in_delta_band") or 0),
        }
    # CSP
    return {
        "otm_puts_in_dte": 0 if error else (trace.get("otm_puts_in_dte") or trace.get("otm_contracts_in_dte") or 0),
        "otm_puts_in_delta_band": 0 if error else (trace.get("otm_puts_in_delta_band") or trace.get("otm_contracts_in_delta_band") or 0),
    }


def build_contract_data_from_canonical(canonical: Dict[str, Any]) -> Dict[str, Any]:
    """Map canonical payload to contract_data shape expected by API and build_eligibility_layers."""
    mode = canonical.get("strategy_mode") or "CSP"
    cd: Dict[str, Any] = {
        "available": canonical.get("chain_available", False),
        "as_of": canonical.get("as_of"),
        "source": "DELAYED" if canonical.get("chain_available") else "NONE",
        "strategy_mode": mode,
        "stage2_trace": _stage2_trace_surface(canonical),
        "expiration_count": len(canonical.get("expirations_in_window") or []),
        "contract_count": canonical.get("response_rows", 0),
        "required_fields_present": canonical.get("required_fields_present", False),
        "rejection_counts": canonical.get("rejection_counts") or {},
        "top_rejection": canonical.get("top_rejection"),
        "spot_used": canonical.get("spot_used"),
        "request_counts": canonical.get("request_counts"),
        "response_rows": canonical.get("response_rows"),
        "contracts_in_delta_band": canonical.get("contracts_in_delta_band"),
        "selected_trade": canonical.get("selected_trade"),
        "samples": canonical.get("samples"),
        "strikes_options_telemetry": {
            "response_rows": canonical.get("response_rows"),
            "puts_requested": (canonical.get("request_counts") or {}).get("puts_requested", 0),
            "calls_requested": (canonical.get("request_counts") or {}).get("calls_requested", 0),
            "sample_request_symbols": (canonical.get("samples") or {}).get("sample_request_symbols"),
        },
        "option_type_counts": {
            "puts_seen": (canonical.get("request_counts") or {}).get("puts_requested", 0),
            "calls_seen": (canonical.get("request_counts") or {}).get("calls_requested", 0),
            "unknown_seen": 0,
        },
    }
    if mode == "CC":
        cd["otm_calls_in_dte"] = canonical.get("otm_calls_in_dte", 0)
        cd["otm_calls_in_delta_band"] = canonical.get("otm_calls_in_delta_band", 0)
    else:
        cd["otm_puts_in_dte"] = canonical.get("otm_puts_in_dte", 0)
        cd["otm_puts_in_delta_band"] = canonical.get("otm_puts_in_delta_band", 0)
    if canonical.get("error_code"):
        cd["error"] = canonical["error_code"]
    return cd


def _stage2_trace_surface(canonical: Dict[str, Any]) -> Dict[str, Any]:
    """Trace surface for API/validate: same keys, no duplication of truth."""
    return {
        "mode": canonical.get("strategy_mode"),
        "spot_used": canonical.get("spot_used"),
        "expirations_in_window": canonical.get("expirations_in_window"),
        "request_counts": canonical.get("request_counts"),
        "response_rows": canonical.get("response_rows"),
        "required_fields_present": canonical.get("required_fields_present"),
        "contracts_in_delta_band": canonical.get("contracts_in_delta_band"),
        "selected_trade": canonical.get("selected_trade"),
        "top_rejection": canonical.get("top_rejection"),
        "top_rejection_reason": canonical.get("top_rejection"),
        "rejection_counts": canonical.get("rejection_counts"),
        "sample_request_symbols": (canonical.get("samples") or {}).get("sample_request_symbols"),
        "top_candidates_table": (canonical.get("samples") or {}).get("top_candidates_table"),
        **{k: canonical.get(k) for k in ("otm_puts_in_dte", "otm_puts_in_delta_band", "otm_calls_in_dte", "otm_calls_in_delta_band") if canonical.get(k) is not None},
    }


def build_candidate_trades_list(strategy_mode: str, selected_trade: Optional[Dict[str, Any]], selected_contract_legacy: Any = None) -> List[Dict[str, Any]]:
    """
    Build candidate_trades list (0 or 1 item). strategy MUST match strategy_mode.
    selected_contract_legacy: optional Stage2 SelectedContract for backward compat (expiry, strike, delta, bid, etc.)
    """
    mode = (strategy_mode or "").strip().upper() or MODE_CSP
    out: List[Dict[str, Any]] = []

    if selected_trade and isinstance(selected_trade, dict):
        exp = selected_trade.get("exp")
        strike = selected_trade.get("strike")
        bid = selected_trade.get("bid")
        delta = selected_trade.get("abs_delta") or selected_trade.get("delta")
        if delta is not None and isinstance(delta, (int, float)) and mode == MODE_CSP and (selected_trade.get("putCall") or "P") == "P":
            delta = -abs(float(delta))
        elif delta is not None and mode == MODE_CC:
            delta = abs(float(delta)) if isinstance(delta, (int, float)) else delta
        max_loss = (float(strike) * 100 - (float(bid or 0) * 100)) if strike is not None and bid is not None else None
        out.append({
            "strategy": mode,
            "expiry": str(exp)[:10] if exp else None,
            "strike": float(strike) if strike is not None else None,
            "delta": float(delta) if delta is not None else None,
            "credit_estimate": float(bid) if bid is not None else None,
            "max_loss": max_loss,
            "why_this_trade": selected_trade.get("why_this_trade") or f"delta={selected_trade.get('abs_delta')}, bid=${bid} ({mode} V2)",
            "liquidity_grade": selected_trade.get("liquidity_grade") or "B",
        })
        return out

    if selected_contract_legacy and getattr(selected_contract_legacy, "contract", None):
        c = selected_contract_legacy.contract
        exp = getattr(c, "expiration", None)
        strike = getattr(c, "strike", None)
        bid = getattr(c.bid, "value", None) if getattr(c, "bid", None) else None
        delta = getattr(c.delta, "value", None) if getattr(c, "delta", None) else None
        max_loss = (float(strike) * 100 - (float(bid or 0) * 100)) if strike is not None and bid is not None else None
        out.append({
            "strategy": mode,
            "expiry": exp.isoformat() if exp else None,
            "strike": float(strike) if strike is not None else None,
            "delta": float(delta) if delta is not None else None,
            "credit_estimate": float(bid) if bid is not None else None,
            "max_loss": max_loss,
            "why_this_trade": getattr(selected_contract_legacy, "selection_reason", "") or f"({mode} V2)",
            "liquidity_grade": c.get_liquidity_grade().value if hasattr(c, "get_liquidity_grade") else "B",
        })
    return out
