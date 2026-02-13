# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.2 – Portfolio Guardrails Layer (Guidance Only).

Guidance only. Non-blocking. No trading logic mutation.
ONLY adjusts suggested contract count (soft override) and adds advisory context.
Does NOT modify eligibility, Stage-2, exit math, sizing core, or auto-block signals.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# Config defaults (editable)
PORTFOLIO_EQUITY_USD = 150_000
TARGET_MAX_EXPOSURE_PCT = 35
MAX_SYMBOL_CONCENTRATION_PCT = 25
MAX_SYMBOL_CRITICAL_PCT = 35


def apply_guardrails(
    portfolio_snapshot: Dict[str, Any],
    candidate: Dict[str, Any],
    regime_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply portfolio guardrails to a candidate signal. Returns adjusted contracts and advisories.

    Consumes:
        portfolio_snapshot: Phase 8.1 snapshot (dict with exposure_pct, symbol_concentration,
            cluster_risk_level, assignment_risk, etc.)
        candidate: {symbol, type (CSP/CC), suggested_contracts, severity, ...}
        regime_state: Optional {mode, throttle_factor}

    Returns:
        {
            "adjusted_contracts": int,
            "severity_override": str | None,
            "advisories": [str],
            "applied_rules": [str]
        }
    """
    advisories: List[str] = []
    applied_rules: List[str] = []
    severity_override: Optional[str] = None

    orig = candidate.get("suggested_contracts") or candidate.get("contracts_suggested") or 0
    try:
        orig_int = max(0, int(orig))
    except (TypeError, ValueError):
        orig_int = 0

    candidate_type = (candidate.get("type") or candidate.get("mode_decision") or "CSP").strip().upper()
    is_csp = candidate_type == "CSP"

    # Start with original; apply multiplicative reductions
    current = float(orig_int)
    regime = regime_state or {}

    # --- Exposure Guardrail ---
    exp_pct = portfolio_snapshot.get("exposure_pct")
    if exp_pct is not None:
        if exp_pct >= TARGET_MAX_EXPOSURE_PCT + 10:  # 45%
            current = 0.0
            severity_override = "ADVISORY"
            advisories.append("Exposure critical (>=%s%%); contracts reduced to 0" % (TARGET_MAX_EXPOSURE_PCT + 10))
            applied_rules.append("exposure_critical")
        elif exp_pct >= TARGET_MAX_EXPOSURE_PCT:  # 35%
            current = math.floor(current * 0.5)
            advisories.append("Exposure high (>=%s%%); contracts halved" % TARGET_MAX_EXPOSURE_PCT)
            applied_rules.append("exposure_guardrail")

    # --- Symbol Concentration ---
    sym_conc = portfolio_snapshot.get("symbol_concentration") or {}
    max_sym_pct = sym_conc.get("max_symbol_pct")
    if max_sym_pct is not None:
        if max_sym_pct >= MAX_SYMBOL_CRITICAL_PCT:
            severity_override = severity_override or "ADVISORY"
            advisories.append("Symbol concentration critical (>=%s%%); severity set ADVISORY" % MAX_SYMBOL_CRITICAL_PCT)
            applied_rules.append("symbol_concentration_critical")
        if max_sym_pct >= MAX_SYMBOL_CONCENTRATION_PCT:
            current = math.floor(current * 0.75)  # reduce by 25%
            advisories.append("Symbol concentration high (>=%s%%); contracts reduced 25%%" % MAX_SYMBOL_CONCENTRATION_PCT)
            applied_rules.append("symbol_concentration")

    # --- Cluster Risk ---
    cluster_level = (portfolio_snapshot.get("cluster_risk_level") or "").strip().upper()
    if cluster_level == "HIGH":
        current = math.floor(current * 0.70)  # reduce by 30%
        advisories.append("Cluster risk HIGH; contracts reduced 30%%")
        applied_rules.append("cluster_risk")

    # --- Regime Throttle ---
    regime_mode = (regime.get("mode") or "").strip().upper()
    if regime_mode == "CRASH":
        current = 0.0
        severity_override = "ADVISORY"
        advisories.append("Regime CRASH; contracts set to 0")
        applied_rules.append("regime_crash")
    elif regime_mode == "DOWN" and is_csp:
        current = math.floor(current * 0.75)  # reduce CSP by 25%
        advisories.append("Regime DOWN; CSP contracts reduced 25%%")
        applied_rules.append("regime_down")

    # --- Assignment Pressure ---
    assign_risk = portfolio_snapshot.get("assignment_risk") or {}
    positions_near_itm = assign_risk.get("positions_near_itm")
    if positions_near_itm is not None and positions_near_itm >= 3:
        current = math.floor(current * 0.60)  # reduce by 40%
        advisories.append("Assignment pressure (>=3 near ITM); contracts reduced 40%%")
        applied_rules.append("assignment_pressure")

    # Final: ensure non-negative integer
    adjusted = max(0, int(math.floor(current)))

    return {
        "adjusted_contracts": adjusted,
        "severity_override": severity_override,
        "advisories": advisories,
        "applied_rules": applied_rules,
    }
