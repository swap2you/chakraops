# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 Shares V2 plan — wraps build_shares_plan_r233 with staged entry + thesis failure."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.shares.shares_plan import build_shares_plan_r233

# Default tranche fractions of sized quantity (sum ≈ 1.0).
DEFAULT_TRANCHE_FRACTIONS: Tuple[float, ...] = (0.50, 0.50)
ALT_TRANCHE_FRACTIONS: Tuple[float, ...] = (0.40, 0.30, 0.30)


def _float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _staged_tranches(qty: int, fractions: Sequence[float]) -> List[Dict[str, Any]]:
    if qty <= 0:
        return []
    fracs = list(fractions) or list(DEFAULT_TRANCHE_FRACTIONS)
    raw = [max(0, int(round(qty * f))) for f in fracs]
    # Adjust rounding so sum equals qty.
    diff = qty - sum(raw)
    if raw and diff != 0:
        raw[-1] = max(0, raw[-1] + diff)
    out: List[Dict[str, Any]] = []
    for i, n in enumerate(raw):
        if n <= 0:
            continue
        out.append({"tranche": i + 1, "shares": n, "fraction": fracs[i] if i < len(fracs) else None})
    return out


def _thesis_failure(
    technicals: Dict[str, Any],
    base_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Flag thesis failure from stop/support break proxies when available."""
    spot = _float(technicals.get("spot")) or _float(base_plan.get("spot"))
    stop = None
    stop_blk = base_plan.get("stop") or {}
    if isinstance(stop_blk, dict):
        stop = _float(stop_blk.get("price"))
    support = _float(technicals.get("support_level"))

    broken_stop = bool(spot is not None and stop is not None and spot < stop)
    broken_support = bool(spot is not None and support is not None and spot < support)
    active = broken_stop or broken_support
    codes: List[str] = []
    if broken_stop:
        codes.append("STOP_BROKEN")
    if broken_support:
        codes.append("SUPPORT_BROKEN")
    if not active and (stop is None and support is None):
        codes.append("THESIS_PROXIES_UNAVAILABLE")
    return {
        "active": active,
        "reason_codes": codes,
        "spot": spot,
        "stop": stop,
        "support": support,
    }


def build_shares_plan_v2(
    summary: Any,
    technicals: Dict[str, Any],
    exit_plan: Optional[Dict[str, Any]] = None,
    hold_time_estimate: Optional[Dict[str, Any]] = None,
    symbol: str = "",
    mtf_levels: Optional[Dict[str, Any]] = None,
    as_of_inputs: Optional[Dict[str, Any]] = None,
    symbol_eligibility: Optional[Dict[str, Any]] = None,
    account_summary: Optional[Dict[str, Any]] = None,
    *,
    tranche_fractions: Optional[Sequence[float]] = None,
    tranche_style: str = "50_50",
) -> Dict[str, Any]:
    """
    Shares V2: base R23.3 plan + staged entry tranches + thesis_failure flag.

    Request-time only. Does not persist to decision_latest.json.
    """
    base = build_shares_plan_r233(
        summary,
        technicals or {},
        exit_plan or {},
        hold_time_estimate,
        symbol,
        mtf_levels=mtf_levels,
        as_of_inputs=as_of_inputs,
        symbol_eligibility=symbol_eligibility,
        account_summary=account_summary,
    )
    sizing = base.get("sizing") or {}
    qty = sizing.get("suggested_shares")
    try:
        qty_i = int(qty) if qty is not None else 0
    except (TypeError, ValueError):
        qty_i = 0

    if tranche_fractions is not None:
        fracs = tuple(tranche_fractions)
    elif (tranche_style or "").strip() in ("40_30_30", "403030"):
        fracs = ALT_TRANCHE_FRACTIONS
    else:
        fracs = DEFAULT_TRANCHE_FRACTIONS

    tranches = _staged_tranches(qty_i, fracs)
    thesis = _thesis_failure(technicals or {}, base)

    out = dict(base)
    out["staged_entry"] = {
        "style": "40_30_30" if fracs == ALT_TRANCHE_FRACTIONS else "50_50",
        "tranches": tranches,
        "total_shares": qty_i,
    }
    out["thesis_failure"] = thesis
    out["manual_only"] = True
    out["trade_execution"] = False
    out["version"] = "shares_v2"
    return out
