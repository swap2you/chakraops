# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.3 – Assignment Stress Simulation Engine (Read-Only Risk Modeling).
Phase 8.3b – Dynamic Stress + NAV Shrink Model (Read-Only).

Read-only risk modeling layer. No trading logic mutation.
Equity is user-supplied (portfolio_equity_usd or equity_usd in snapshot).
CSP reserved cash is not additive on assignment — avoid double count.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Survival status thresholds (Phase 8.3b; tunable)
SURVIVAL_OK_BUFFER_PCT = 0.20  # cash_buffer >= 20% of equity -> OK
SURVIVAL_TIGHT_BUFFER_PCT = 0.05  # 5–20% -> TIGHT; <5% -> CRITICAL


def _position_mode(pos: Dict[str, Any]) -> str:
    """Normalize position mode/type to CSP or CC."""
    m = (pos.get("mode") or pos.get("type") or "CSP").strip().upper()
    return "CC" if m == "CC" else "CSP"


def _get_spot(pos: Dict[str, Any]) -> Optional[float]:
    """Get current spot from position (spot, current_spot, entry_spot)."""
    for k in ("spot", "current_spot", "entry_spot"):
        v = pos.get(k)
        if v is not None:
            try:
                f = float(v)
                if f > 0:
                    return f
            except (TypeError, ValueError):
                pass
    return None


def simulate_assignment_stress(
    portfolio_snapshot: Dict[str, Any],
    open_positions: List[Dict[str, Any]],
    shock_levels: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Simulate portfolio shock scenarios. CSP positions only; deterministic math.

    Args:
        portfolio_snapshot: Phase 8.1 snapshot (total_capital_committed, exposure_pct).
        open_positions: List of position dicts with spot, strike, contracts, mode.
        shock_levels: Shock percentages (e.g. -0.05 = 5% down). Default [-0.05, -0.10, -0.15].

    Returns:
        {
            "scenarios": [{"shock_pct", "estimated_assignments", "assignment_capital_required",
                          "estimated_unrealized_drawdown", "post_shock_exposure_pct"}],
            "worst_case": {"shock_pct", "assignment_capital_required", "estimated_unrealized_drawdown"},
            "warnings": []
        }
    """
    warnings: List[str] = []
    levels = shock_levels if shock_levels is not None else [-0.05, -0.10, -0.15]

    # Filter CSP positions with spot and strike
    csp_positions: List[Dict[str, Any]] = []
    for pos in open_positions:
        if _position_mode(pos) != "CSP":
            continue
        spot = _get_spot(pos)
        strike = pos.get("strike")
        contracts = int(pos.get("contracts") or 0)
        if spot is None or strike is None:
            sym = pos.get("symbol") or pos.get("position_id") or "?"
            warnings.append("CSP position %s missing spot or strike; skipped" % sym)
            continue
        if contracts <= 0:
            continue
        csp_positions.append({
            "spot": float(spot),
            "strike": float(strike),
            "contracts": int(contracts),
        })

    existing_committed = float(portfolio_snapshot.get("total_capital_committed") or 0)
    # Derive portfolio_equity from snapshot if exposure_pct available
    exp_pct = portfolio_snapshot.get("exposure_pct")
    portfolio_equity: Optional[float] = None
    if exp_pct is not None and exp_pct > 0 and existing_committed > 0:
        try:
            portfolio_equity = existing_committed / (exp_pct / 100.0)
        except (TypeError, ZeroDivisionError):
            pass

    scenarios: List[Dict[str, Any]] = []

    if not csp_positions:
        return {
            "scenarios": [],
            "worst_case": {
                "shock_pct": levels[-1] if levels else None,
                "assignment_capital_required": 0.0,
                "estimated_unrealized_drawdown": 0.0,
            },
            "warnings": warnings,
        }

    for shock_pct in levels:
        total_assignments = 0
        total_capital_required = 0.0
        total_drawdown = 0.0

        for p in csp_positions:
            spot = p["spot"]
            strike = p["strike"]
            contracts = p["contracts"]
            new_spot = spot * (1.0 + shock_pct)

            if new_spot <= strike:
                cap = strike * 100 * contracts
                total_assignments += contracts
                total_capital_required += cap
                unrealized_per = max(0.0, (strike - new_spot) * 100)
                total_drawdown += unrealized_per * contracts

        total_drawdown = max(0.0, total_drawdown)
        post_shock_exposure_pct: Optional[float] = None
        if portfolio_equity is not None and portfolio_equity > 0:
            post_shock_exposure_pct = 100.0 * (existing_committed + total_capital_required) / portfolio_equity

        scenarios.append({
            "shock_pct": shock_pct,
            "estimated_assignments": total_assignments,
            "assignment_capital_required": total_capital_required,
            "estimated_unrealized_drawdown": total_drawdown,
            "post_shock_exposure_pct": post_shock_exposure_pct,
        })

    # Worst-case: scenario with largest unrealized_drawdown
    worst = max(scenarios, key=lambda s: s.get("estimated_unrealized_drawdown", 0))
    worst_case = {
        "shock_pct": worst["shock_pct"],
        "assignment_capital_required": worst["assignment_capital_required"],
        "estimated_unrealized_drawdown": worst["estimated_unrealized_drawdown"],
    }

    return {
        "scenarios": scenarios,
        "worst_case": worst_case,
        "warnings": warnings,
    }


def format_stress_summary(simulation_result: Dict[str, Any]) -> str:
    """
    Return human-readable summary. Phase 8.4 UI helper; not auto-sent.

    Example: "Stress -10%: 3 assignments, $45,000 capital, $6,200 est drawdown"
    """
    lines: List[str] = []
    for s in simulation_result.get("scenarios") or []:
        shock = s.get("shock_pct", 0)
        shock_pct = int(shock * 100)
        assignments = s.get("estimated_assignments", 0)
        cap = int(s.get("assignment_capital_required", 0))
        dd = int(s.get("estimated_unrealized_drawdown", 0))
        lines.append(
            "Stress %s%%: %s assignments, $%s capital, $%s est drawdown"
            % (shock_pct, assignments, f"{cap:,}", f"{dd:,}")
        )
    return "\n".join(lines) if lines else "No stress scenarios"


def format_stress_summary_dynamic(simulation_result: Dict[str, Any]) -> str:
    """
    Phase 8.3b: Human-readable summary with survival_status and cash_buffer.
    Not auto-sent; used in Phase 8.4 UI.
    """
    lines: List[str] = []
    for s in simulation_result.get("scenarios") or []:
        shock = s.get("shock_pct", 0)
        shock_pct = int(shock * 100)
        assignments = s.get("estimated_assignments", 0)
        cap = int(s.get("assignment_capital_required", 0))
        dd = int(s.get("estimated_unrealized_drawdown", 0))
        buf = s.get("cash_buffer")
        status = s.get("survival_status", "UNKNOWN")
        buf_s = "$%s" % f"{int(buf):,}" if buf is not None else "N/A"
        lines.append(
            "Stress %s%%: %s assignments, $%s capital, $%s drawdown | buffer %s, %s"
            % (shock_pct, assignments, f"{cap:,}", f"{dd:,}", buf_s, status)
        )
    return "\n".join(lines) if lines else "No stress scenarios"


def _cc_equity_notional(pos: Dict[str, Any], warnings: List[str]) -> float:
    """CC notional: shares * (cost_basis_per_share or entry_spot). 0 + warning if missing."""
    shares = pos.get("shares") or pos.get("quantity")
    contracts = int(pos.get("contracts") or 0)
    if shares is None:
        shares = contracts * 100
    else:
        shares = int(shares)
    cost = pos.get("cost_basis_per_share") or pos.get("entry_spot")
    if cost is None:
        sym = pos.get("symbol") or pos.get("position_id") or "?"
        warnings.append("CC position %s missing cost_basis/entry_spot; notional=0" % sym)
        return 0.0
    if shares <= 0:
        return 0.0
    return float(shares) * float(cost)


def simulate_assignment_stress_dynamic(
    portfolio_snapshot: Dict[str, Any],
    open_positions: List[Dict[str, Any]],
    shock_levels: Optional[List[float]] = None,
    nav_shrink_mode: str = "CONSERVATIVE",
) -> Dict[str, Any]:
    """
    Phase 8.3b: Dynamic stress with NAV shrink. Equity from snapshot (user-supplied).

    Returns scenarios with shocked_equity, post_shock_exposure, cash_buffer, survival_status.
    CSP reserved cash is not additive on assignment (avoid double count).
    """
    warnings: List[str] = []
    levels = shock_levels if shock_levels is not None else [-0.05, -0.10, -0.15]
    mode = (nav_shrink_mode or "CONSERVATIVE").strip().upper()
    if mode not in ("CONSERVATIVE", "LINEAR"):
        mode = "CONSERVATIVE"

    # Equity source: portfolio_equity_usd or equity_usd; do NOT call broker
    starting_equity: Optional[float] = None
    for k in ("portfolio_equity_usd", "equity_usd"):
        v = portfolio_snapshot.get(k)
        if v is not None:
            try:
                f = float(v)
                if f > 0:
                    starting_equity = f
                    break
            except (TypeError, ValueError):
                pass

    # CSP reserved cash (all CSPs) and CC equity notional
    csp_reserved_cash = 0.0
    cc_positions: List[Dict[str, Any]] = []
    csp_positions: List[Dict[str, Any]] = []

    for pos in open_positions:
        pm = _position_mode(pos)
        contracts = int(pos.get("contracts") or 0)
        if pm == "CSP":
            strike = pos.get("strike")
            if strike is not None and contracts > 0:
                csp_reserved_cash += float(strike) * 100 * contracts
            spot = _get_spot(pos)
            if spot is not None and strike is not None and contracts > 0:
                csp_positions.append({
                    "spot": float(spot),
                    "strike": float(strike),
                    "contracts": contracts,
                })
            elif spot is None or strike is None:
                sym = pos.get("symbol") or pos.get("position_id") or "?"
                warnings.append("CSP position %s missing spot or strike; skipped" % sym)
        else:
            cc_positions.append(pos)

    cc_equity_notional = sum(_cc_equity_notional(p, warnings) for p in cc_positions)
    total_current_notional = csp_reserved_cash + cc_equity_notional

    scenarios: List[Dict[str, Any]] = []

    if not csp_positions and not cc_positions:
        for shock_pct in levels:
            scenarios.append(_dynamic_scenario_empty(
                shock_pct, starting_equity, csp_reserved_cash, cc_equity_notional, warnings
            ))
    else:
        for shock_pct in levels:
            # Assignment detection (CSP only)
            total_assignments = 0
            assignment_capital_required = 0.0
            estimated_unrealized_drawdown = 0.0

            for p in csp_positions:
                spot, strike, contracts = p["spot"], p["strike"], p["contracts"]
                new_spot = spot * (1.0 + shock_pct)
                if new_spot <= strike:
                    cap = strike * 100 * contracts
                    total_assignments += contracts
                    assignment_capital_required += cap
                    unrealized_per = max(0.0, (strike - new_spot) * 100)
                    estimated_unrealized_drawdown += unrealized_per * contracts

            estimated_unrealized_drawdown = max(0.0, estimated_unrealized_drawdown)

            # CC equity notional shocked
            cc_equity_notional_shocked = 0.0
            cc_shock_note = False
            for pos in cc_positions:
                spot = _get_spot(pos)
                shares = pos.get("shares") or pos.get("quantity")
                contracts = int(pos.get("contracts") or 0)
                if shares is None:
                    shares = contracts * 100
                else:
                    shares = int(shares)
                if spot is not None and shares > 0:
                    new_spot_cc = float(spot) * (1.0 + shock_pct)
                    cc_equity_notional_shocked += shares * new_spot_cc
                else:
                    cc_equity_notional_shocked += _cc_equity_notional(pos, [])
                    cc_shock_note = True

            # post_shock_total_notional = cc_shocked + csp_reserved (no double count)
            total_notional_post_shock = cc_equity_notional_shocked + csp_reserved_cash

            # NAV shrink
            shocked_equity: Optional[float] = None
            equity_drawdown_pct: Optional[float] = None
            if starting_equity is not None and starting_equity > 0:
                if mode == "CONSERVATIVE":
                    shocked_equity = max(0.0, starting_equity - estimated_unrealized_drawdown)
                else:
                    shocked_equity = max(0.0, starting_equity * (1.0 + shock_pct) - 0.0)
                if starting_equity > 0:
                    equity_drawdown_pct = 100.0 * (estimated_unrealized_drawdown / starting_equity)

            post_shock_exposure_pct: Optional[float] = None
            if shocked_equity is not None and shocked_equity > 0:
                post_shock_exposure_pct = 100.0 * total_notional_post_shock / shocked_equity

            cash_buffer: Optional[float] = None
            if starting_equity is not None:
                cash_buffer = starting_equity - assignment_capital_required

            survival_status = "UNKNOWN"
            if starting_equity is not None and starting_equity > 0 and cash_buffer is not None:
                buf_pct = cash_buffer / starting_equity
                if buf_pct >= SURVIVAL_OK_BUFFER_PCT:
                    survival_status = "OK"
                elif buf_pct >= SURVIVAL_TIGHT_BUFFER_PCT:
                    survival_status = "TIGHT"
                else:
                    survival_status = "CRITICAL"

            notes: List[str] = []
            if cc_shock_note:
                notes.append("CC notional used pre-shock (no spot)")

            scenarios.append({
                "shock_pct": shock_pct,
                "estimated_assignments": total_assignments,
                "assignment_capital_required": assignment_capital_required,
                "estimated_unrealized_drawdown": estimated_unrealized_drawdown,
                "starting_equity": starting_equity,
                "shocked_equity": shocked_equity,
                "equity_drawdown_pct": equity_drawdown_pct,
                "csp_reserved_cash": csp_reserved_cash,
                "cc_equity_notional": cc_equity_notional,
                "total_notional_post_shock": total_notional_post_shock,
                "post_shock_exposure_pct": post_shock_exposure_pct,
                "cash_buffer": cash_buffer,
                "survival_status": survival_status,
                "notes": notes,
            })

    # Worst-case: largest unrealized_drawdown; tie-break most negative shock
    if scenarios:
        worst = max(
            scenarios,
            key=lambda s: (s.get("estimated_unrealized_drawdown", 0), -(s.get("shock_pct") or 0))
        )
        worst_case = {
            "shock_pct": worst["shock_pct"],
            "estimated_unrealized_drawdown": worst["estimated_unrealized_drawdown"],
            "shocked_equity": worst.get("shocked_equity"),
            "post_shock_exposure_pct": worst.get("post_shock_exposure_pct"),
            "cash_buffer": worst.get("cash_buffer"),
            "survival_status": worst.get("survival_status", "UNKNOWN"),
        }
    else:
        worst_case = {
            "shock_pct": levels[-1] if levels else None,
            "estimated_unrealized_drawdown": 0.0,
            "shocked_equity": None,
            "post_shock_exposure_pct": None,
            "cash_buffer": None,
            "survival_status": "UNKNOWN",
        }

    return {
        "scenarios": scenarios,
        "worst_case": worst_case,
        "warnings": warnings,
    }


def _dynamic_scenario_empty(
    shock_pct: float,
    starting_equity: Optional[float],
    csp_reserved_cash: float,
    cc_equity_notional: float,
    warnings: List[str],
) -> Dict[str, Any]:
    """Build empty scenario when no CSP/CC positions."""
    total_notional = csp_reserved_cash + cc_equity_notional
    shocked_equity = starting_equity
    post_shock_exposure_pct: Optional[float] = None
    if shocked_equity is not None and shocked_equity > 0 and total_notional > 0:
        post_shock_exposure_pct = 100.0 * total_notional / shocked_equity
    cash_buffer = (starting_equity - 0.0) if starting_equity is not None else None
    survival_status = "UNKNOWN"
    if starting_equity and starting_equity > 0 and cash_buffer is not None:
        buf_pct = cash_buffer / starting_equity
        survival_status = "OK" if buf_pct >= SURVIVAL_OK_BUFFER_PCT else "TIGHT" if buf_pct >= SURVIVAL_TIGHT_BUFFER_PCT else "CRITICAL"
    return {
        "shock_pct": shock_pct,
        "estimated_assignments": 0,
        "assignment_capital_required": 0.0,
        "estimated_unrealized_drawdown": 0.0,
        "starting_equity": starting_equity,
        "shocked_equity": shocked_equity,
        "equity_drawdown_pct": None,
        "csp_reserved_cash": csp_reserved_cash,
        "cc_equity_notional": cc_equity_notional,
        "total_notional_post_shock": total_notional,
        "post_shock_exposure_pct": post_shock_exposure_pct,
        "cash_buffer": cash_buffer,
        "survival_status": survival_status,
        "notes": [],
    }
