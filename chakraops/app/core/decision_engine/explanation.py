# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Per-recommendation explainability contract (R36.1).

Pure, additive builder: given one live recommendation item (the dict produced by
``legacy_adapter.to_live_recommendations`` / ``live_service``) plus the resolved
profile dict, produce a structured explanation. This module NEVER changes the
decision, NEVER invents data (absent inputs stay ``None``), and NEVER converts a
rejection into a recommendation.

Advisory-only: the contract echoes ``manual_only=True`` / ``trade_execution=False``
and contains no order/broker fields.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.decision_engine import reason_registry as R

# Unit-aware near-miss epsilons (documented; boundary-tested). A near miss is a
# SOFT (temporary) gate that missed its threshold by no more than the epsilon.
DELTA_NEAR_MISS_EPS = 0.02          # absolute delta
DTE_NEAR_MISS_EPS_DAYS = 3          # days
RETURN_NEAR_MISS_EPS_PCT = 0.25     # percentage points

# Floating-point tolerance so exact-boundary near-misses are inclusive.
_FLOAT_TOL = 1e-9

_SEV_ORDER = {R.SEV_HARD: 3, R.SEV_SOFT: 2, R.SEV_INFO: 1}
_SOFT_RANGE_CODES = ("DELTA_OUT_OF_RANGE", "DTE_OUT_OF_RANGE", "BELOW_RETURN_THRESHOLD")


def _num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _freshness_input(item: Dict[str, Any], label: str) -> Dict[str, Any]:
    df = item.get("data_freshness") or {}
    for row in (df.get("inputs") or []):
        if isinstance(row, dict) and row.get("label") == label:
            return row
    return {}


def _delta_range(profile: Dict[str, Any], strategy: Optional[str]) -> Optional[Tuple[float, float]]:
    if not profile:
        return None
    key = "csp_delta_range" if strategy == "CSP" else "cc_delta_range" if strategy == "COVERED_CALL" else None
    rng = profile.get(key) if key else None
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        return (float(rng[0]), float(rng[1]))
    return None


def _dte_range(profile: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    rng = (profile or {}).get("dte_range")
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        return (float(rng[0]), float(rng[1]))
    return None


def _measured(item: Dict[str, Any], field_path: Optional[str]) -> Optional[float]:
    if not field_path:
        return None
    sc = item.get("selected_contract") or {}
    if field_path == "selected_contract.delta":
        d = _num(sc.get("delta"))
        return abs(d) if d is not None else None
    if field_path == "selected_contract.dte":
        return _num(sc.get("dte"))
    if field_path == "selected_contract.open_interest":
        return _num(sc.get("open_interest"))
    if field_path == "selected_contract.volume":
        return _num(sc.get("volume"))
    if field_path == "selected_contract.bid_ask_spread_pct":
        return _num(sc.get("bid_ask_spread_pct"))
    if field_path == "expected_return_pct":
        return _num(item.get("expected_return_pct"))
    if field_path == "sizing.shares_held":
        return _num((item.get("sizing") or {}).get("shares_held"))
    if field_path == "event_risk.earnings_days":
        return _num((item.get("event_risk") or {}).get("earnings_days"))
    if field_path.startswith("data_freshness."):
        _, label, attr = field_path.split(".", 2)
        return _num(_freshness_input(item, label).get(attr))
    return None


def _threshold(item: Dict[str, Any], profile: Dict[str, Any], strategy: Optional[str],
               field_path: Optional[str]) -> Any:
    if not field_path:
        return None
    if field_path == "profile.delta_range":
        return _delta_range(profile, strategy)
    if field_path == "profile.dte_range":
        return _dte_range(profile)
    if field_path == "profile.min_return_pct":
        return _num((profile or {}).get("min_return_pct"))
    if field_path == "profile.liquidity.min_open_interest":
        return _num(((profile or {}).get("liquidity") or {}).get("min_open_interest"))
    if field_path == "profile.liquidity.min_volume":
        return _num(((profile or {}).get("liquidity") or {}).get("min_volume"))
    if field_path == "profile.liquidity.max_bid_ask_spread_pct":
        return _num(((profile or {}).get("liquidity") or {}).get("max_bid_ask_spread_pct"))
    if field_path == "profile.max_sector_exposure_pct":
        return _num((profile or {}).get("max_sector_exposure_pct"))
    if field_path == "const.100":
        return 100.0
    if field_path == "event_risk.blackout_days":
        return _num((item.get("event_risk") or {}).get("blackout_days"))
    if field_path.startswith("data_freshness."):
        _, label, attr = field_path.split(".", 2)
        return _num(_freshness_input(item, label).get(attr))
    return None


def _within(code: str, measured: Optional[float], threshold: Any) -> Optional[bool]:
    if measured is None or threshold is None:
        return None
    if isinstance(threshold, tuple):
        lo, hi = threshold
        return lo <= measured <= hi
    if code in ("LOW_OPEN_INTEREST", "LOW_VOLUME", "MEETS_RETURN_THRESHOLD", "BELOW_RETURN_THRESHOLD"):
        return measured >= float(threshold)
    if code == "WIDE_SPREAD":
        return measured <= float(threshold)
    if code == "EARNINGS_BLACKOUT":
        return measured > float(threshold)  # outside blackout is "within" (safe)
    return None


def _comparator(code: str, threshold: Any) -> str:
    if isinstance(threshold, tuple):
        return "in_range"
    if code in ("LOW_OPEN_INTEREST", "LOW_VOLUME", "MEETS_RETURN_THRESHOLD", "BELOW_RETURN_THRESHOLD"):
        return ">="
    if code == "WIDE_SPREAD":
        return "<="
    if code == "EARNINGS_BLACKOUT":
        return ">"
    return "=="


def _measured_values(item: Dict[str, Any], profile: Dict[str, Any],
                     resolved: List[R.ReasonCode], strategy: Optional[str]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for rc in resolved:
        if not rc.measured_field or not rc.threshold_field:
            continue
        if rc.code in seen:
            continue
        measured = _measured(item, rc.measured_field)
        threshold = _threshold(item, profile, strategy, rc.threshold_field)
        if measured is None and threshold is None:
            continue
        seen.add(rc.code)
        thr_repr = list(threshold) if isinstance(threshold, tuple) else threshold
        out.append({
            "code": rc.code,
            "name": rc.title,
            "measured": measured,
            "threshold": thr_repr,
            "unit": rc.unit,
            "comparator": _comparator(rc.code, threshold),
            "within": _within(rc.code, measured, threshold),
        })
    return out


def compute_near_miss(item: Dict[str, Any], profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deterministic, strategy/unit-aware near-miss detection.

    A near miss is ONLY possible for soft (temporary) range gates that missed by
    <= the unit-specific epsilon. It is NEVER a near miss when the item is BLOCKED
    or when any safety-critical reason is present, and it NEVER changes status.
    """
    item = item or {}
    profile = profile or {}
    strategy = item.get("strategy")
    codes = list(item.get("reason_codes") or [])

    if item.get("decision_status") == "BLOCKED" or any(R.is_safety_critical(c) for c in codes):
        return {"is_near_miss": False, "blocked_by_safety_critical": True}

    candidates: List[Dict[str, Any]] = []

    if "DELTA_OUT_OF_RANGE" in codes:
        measured = _measured(item, "selected_contract.delta")
        rng = _delta_range(profile, strategy)
        if measured is not None and rng is not None:
            lo, hi = rng
            if measured < lo or measured > hi:
                dist = min(abs(measured - lo), abs(measured - hi))
                if dist <= DELTA_NEAR_MISS_EPS + _FLOAT_TOL:
                    candidates.append({"gate": "DELTA_OUT_OF_RANGE", "measured": measured,
                                       "threshold": [lo, hi], "unit": "delta", "distance": round(dist, 4),
                                       "eps": DELTA_NEAR_MISS_EPS, "norm": dist / DELTA_NEAR_MISS_EPS})

    if "DTE_OUT_OF_RANGE" in codes:
        measured = _measured(item, "selected_contract.dte")
        rng = _dte_range(profile)
        if measured is not None and rng is not None:
            lo, hi = rng
            if measured < lo or measured > hi:
                dist = min(abs(measured - lo), abs(measured - hi))
                if dist <= DTE_NEAR_MISS_EPS_DAYS + _FLOAT_TOL:
                    candidates.append({"gate": "DTE_OUT_OF_RANGE", "measured": measured,
                                       "threshold": [lo, hi], "unit": "days", "distance": round(dist, 4),
                                       "eps": DTE_NEAR_MISS_EPS_DAYS, "norm": dist / DTE_NEAR_MISS_EPS_DAYS})

    if "BELOW_RETURN_THRESHOLD" in codes:
        measured = _measured(item, "expected_return_pct")
        threshold = _num(profile.get("min_return_pct"))
        if measured is not None and threshold is not None and measured < threshold:
            dist = threshold - measured
            if dist <= RETURN_NEAR_MISS_EPS_PCT + _FLOAT_TOL:
                candidates.append({"gate": "BELOW_RETURN_THRESHOLD", "measured": measured,
                                   "threshold": threshold, "unit": "pct", "distance": round(dist, 4),
                                   "eps": RETURN_NEAR_MISS_EPS_PCT, "norm": dist / RETURN_NEAR_MISS_EPS_PCT})

    if not candidates:
        return {"is_near_miss": False}

    # Deterministic pick: smallest normalized distance, then gate name.
    best = sorted(candidates, key=lambda c: (c["norm"], c["gate"]))[0]
    return {
        "is_near_miss": True,
        "gate": best["gate"],
        "measured": best["measured"],
        "threshold": best["threshold"],
        "unit": best["unit"],
        "distance": best["distance"],
        "epsilon": best["eps"],
        "note": f"Missed {best['gate']} by {best['distance']} {best['unit']} (<= {best['eps']}).",
    }


def _calc_trace(item: Dict[str, Any], measured_values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    price_row = _freshness_input(item, "PRICE")
    chain_row = _freshness_input(item, "OPTIONS_CHAIN")
    formulas = {
        "expected_return_pct": "return_pct = premium / collateral * 100",
        "selected_contract.delta": "measured = abs(contract.delta)",
        "selected_contract.dte": "measured = contract.days_to_expiry",
        "selected_contract.bid_ask_spread_pct": "measured = (ask - bid) / mid * 100",
    }
    src_ts = {
        "expected_return_pct": chain_row.get("as_of_utc"),
        "selected_contract.delta": chain_row.get("as_of_utc"),
        "selected_contract.dte": chain_row.get("as_of_utc"),
        "selected_contract.open_interest": chain_row.get("as_of_utc"),
        "selected_contract.volume": chain_row.get("as_of_utc"),
        "selected_contract.bid_ask_spread_pct": chain_row.get("as_of_utc"),
    }
    trace: List[Dict[str, Any]] = []
    for mv in measured_values:
        rc = R.resolve(mv["code"])
        mf = rc.measured_field
        trace.append({
            "input": mv["name"],
            "value": mv["measured"],
            "unit": mv["unit"],
            "source": rc.data_source or ("profile" if mf and mf.startswith("profile") else "computed"),
            "timestamp": src_ts.get(mf) or (price_row.get("as_of_utc") if mf == "expected_return_pct" else None),
            "formula": formulas.get(mf),
            "threshold": mv["threshold"],
            "comparator": mv["comparator"],
            "output": mv["within"],
            "rounding": "values shown as provided by ORATS; percentages to 2 dp in UI",
        })
    return trace


def _data_sources(item: Dict[str, Any], resolved: List[R.ReasonCode]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for label in ("PRICE", "OPTIONS_CHAIN"):
        row = _freshness_input(item, label)
        if row:
            out.append({"name": label, "as_of_utc": row.get("as_of_utc"), "status": row.get("status")})
    names = {s["name"] for s in out}
    for rc in resolved:
        if rc.data_source and rc.data_source not in names:
            names.add(rc.data_source)
            out.append({"name": rc.data_source, "as_of_utc": None, "status": None})
    return out


def build_explanation(item: Optional[Dict[str, Any]], profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the additive explainability contract for one live recommendation item."""
    item = item or {}
    profile = profile or {}
    strategy = item.get("strategy")

    codes = list(item.get("reason_codes") or [])
    flags = [f for f in (item.get("risk_flags") or []) if f not in codes]
    all_codes = codes + flags
    resolved = [R.resolve(c) for c in all_codes]

    # Primary = highest severity, preserving original order for ties.
    primary_rc: Optional[R.ReasonCode] = None
    primary_rank = -1
    for rc in resolved:
        rank = _SEV_ORDER.get(rc.severity, 0)
        if rank > primary_rank:
            primary_rank = rank
            primary_rc = rc
    supporting = [rc for rc in resolved if rc is not primary_rc]

    measured_values = _measured_values(item, profile, resolved, strategy)
    near_miss = compute_near_miss(item, profile)
    calc_trace = _calc_trace(item, measured_values)

    passed_gates = [rc.code for rc in resolved if rc.severity == R.SEV_INFO]
    failed_gates = [rc.code for rc in resolved if rc.severity in (R.SEV_HARD, R.SEV_SOFT)]
    temporary_reasons = [rc.code for rc in resolved if rc.klass == R.KLASS_TEMPORARY]
    safety_critical_reasons = [rc.code for rc in resolved if rc.klass == R.KLASS_SAFETY_CRITICAL]

    event_risk = item.get("event_risk") or {}
    sizing = item.get("sizing") or {}

    return {
        "symbol": item.get("symbol"),
        "strategy": strategy,
        "profile": item.get("profile") or profile.get("name"),
        "decision_status": item.get("decision_status"),
        "manual_only": True,
        "trade_execution": False,
        "primary_reason": primary_rc.to_dict() if primary_rc else None,
        "supporting_reasons": [rc.to_dict() for rc in supporting],
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "measured_values": measured_values,
        "near_miss": near_miss,
        "calculation_trace": calc_trace,
        "data_sources": _data_sources(item, resolved),
        "timestamps": {
            "price_as_of": _freshness_input(item, "PRICE").get("as_of_utc"),
            "chain_as_of": _freshness_input(item, "OPTIONS_CHAIN").get("as_of_utc"),
        },
        "event_risk": {
            "earnings_days": event_risk.get("earnings_days"),
            "blackout_days": event_risk.get("blackout_days"),
        },
        "portfolio_impact": {
            "capital_required": item.get("capital_required"),
            "contracts": sizing.get("contracts"),
            "shares": sizing.get("shares"),
            "expected_return_pct": item.get("expected_return_pct"),
            "expected_return_dollars": item.get("expected_return_dollars"),
        },
        "temporary_reasons": temporary_reasons,
        "safety_critical_reasons": safety_critical_reasons,
    }
