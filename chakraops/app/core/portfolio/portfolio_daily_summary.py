# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.5 – Portfolio Daily Summary (Read-Only).

Read-only formatter for DAILY Slack message.
Builds structured dict ready for Slack text. No trading logic mutation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

TARGET_MAX_EXPOSURE_PCT = 35


def _exposure_status(exposure_pct: Optional[float]) -> str:
    """Exposure color: GREEN < 70% target, YELLOW 70–100%, RED >= target."""
    if exposure_pct is None:
        return "N/A"
    target = TARGET_MAX_EXPOSURE_PCT
    pct_of_target = exposure_pct / target if target > 0 else 0
    if pct_of_target < 0.70:
        return "GREEN"
    if pct_of_target < 1.0:
        return "YELLOW"
    return "RED"


def _str_capital(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return "$%s" % (int(float(v)))
    except (TypeError, ValueError):
        return str(v)


def build_portfolio_daily_summary(
    snapshot: Dict[str, Any],
    stress_dynamic: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build Portfolio Risk Summary dict for DAILY Slack message.

    Returns:
        {
            "title": "Portfolio Risk Summary",
            "lines": [...]
        }
    """
    lines: List[str] = []
    equity = snapshot.get("portfolio_equity_usd") or snapshot.get("equity_usd")
    exposure_pct = snapshot.get("exposure_pct")
    status = _exposure_status(exposure_pct)
    open_csp = snapshot.get("open_csp_count") or 0
    open_cc = snapshot.get("open_cc_count") or 0
    max_sym_pct = snapshot.get("symbol_concentration") or {}
    max_sym = max_sym_pct.get("max_symbol_pct")
    cluster = (snapshot.get("cluster_risk_level") or "UNKNOWN").strip().upper()

    # Line 1: Equity | Target Max Exposure
    lines.append("Equity: %s | Target Max Exposure: %s%%" % (_str_capital(equity), TARGET_MAX_EXPOSURE_PCT))

    # Line 2: Exposure | Open CSP | Open CC
    exp_s = "%.1f%%" % exposure_pct if exposure_pct is not None else "N/A"
    lines.append("Exposure: %s (%s) | Open CSP: %s | Open CC: %s" % (exp_s, status, open_csp, open_cc))

    # Line 3: Max Symbol Concentration | Cluster Risk
    sym_s = "%.0f%%" % max_sym if max_sym is not None else "N/A"
    lines.append("Max Symbol Concentration: %s | Cluster Risk: %s" % (sym_s, cluster))

    # Stress: prefer -10% scenario
    scenarios = stress_dynamic.get("scenarios") or []
    stress_10 = next((s for s in scenarios if s.get("shock_pct") == -0.10), None)
    if stress_10:
        assigns = stress_10.get("estimated_assignments", 0)
        cap = stress_10.get("assignment_capital_required", 0)
        dd = stress_10.get("estimated_unrealized_drawdown", 0)
        exp_ps = stress_10.get("post_shock_exposure_pct")
        exp_ps_s = "%.1f%%" % exp_ps if exp_ps is not None else "N/A"
        surv = stress_10.get("survival_status") or "UNKNOWN"
        lines.append("Stress -10%%: %s assigns | %s capital | %s drawdown | Exposure: %s | Survival: %s" % (
            assigns, _str_capital(cap), _str_capital(dd), exp_ps_s, surv,
        ))

    # Worst case (worst_case dict may omit assignment_capital_required; look up from scenarios)
    worst = stress_dynamic.get("worst_case") or {}
    wc_shock = worst.get("shock_pct")
    wc_shock_s = "%.0f%%" % (wc_shock * 100) if wc_shock is not None else "?"
    wc_cap = worst.get("assignment_capital_required")
    if wc_cap is None and wc_shock is not None:
        match = next((s for s in scenarios if s.get("shock_pct") == wc_shock), None)
        wc_cap = match.get("assignment_capital_required") if match else None
    wc_dd = worst.get("estimated_unrealized_drawdown")
    wc_surv = worst.get("survival_status") or "UNKNOWN"
    lines.append("Worst Case: %s | %s capital | %s drawdown | Survival: %s" % (
        wc_shock_s, _str_capital(wc_cap), _str_capital(wc_dd), wc_surv,
    ))

    # Warnings
    snap_warn = snapshot.get("warnings") or []
    stress_warn = stress_dynamic.get("warnings") or []
    all_warn = snap_warn + stress_warn
    if all_warn:
        condensed = all_warn[:2]
        condensed_text = "; ".join(condensed)
        if len(condensed_text) > 80:
            condensed_text = condensed_text[:80] + "..."
        lines.append("Warnings: %s (%s)" % (len(all_warn), condensed_text))
    else:
        lines.append("Warnings: 0")

    return {
        "title": "Portfolio Risk Summary",
        "lines": lines,
    }
