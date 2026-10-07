# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R68 guarded strategy builder — Stay in Cash valid; never promises returns."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.strategy.payoff_r68 import calculate_short_put_payoff

SCENARIOS = ("conservative", "balanced", "aggressive")


def csp_payoff(*, strike: float, credit: float, spot: Optional[float] = None) -> Dict[str, Any]:
    """CSP breakeven/max-profit helper used by golive API + acceptance tests."""
    out = calculate_short_put_payoff(strike=strike, premium=credit, contracts=1)
    out["credit"] = float(credit)
    out["spot"] = float(spot) if spot is not None else None
    out["return_guarantee"] = False
    return out


def build_strategy_plan(
    *,
    capital: Optional[float] = None,
    account: Optional[str] = None,
    account_alias: Optional[str] = None,
    horizon_days: Optional[int] = None,
    horizon_months: Optional[int] = None,
    income_growth_priority: str = "balanced",  # income|growth|balanced
    max_drawdown_tolerance: Optional[float] = None,
    max_drawdown_pct: Optional[float] = None,
    liquidity_need: str = "normal",  # high|normal|low
    assignment_comfort: str = "medium",  # low|medium|high
    concentration_limit_pct: Optional[float] = None,
    target_return_pct: Optional[float] = None,
    scenario: str = "balanced",
    data_trustworthy: bool = True,
) -> Dict[str, Any]:
    """Produce an advisory strategy plan. May return Stay in Cash.

    Target return is treated as a goal label only — never a promise.
    """
    acct = (account_alias or account or "acct_individual").strip() or "acct_individual"
    if horizon_days is None:
        if horizon_months is not None:
            horizon_days = max(1, int(horizon_months) * 30)
        else:
            horizon_days = 30
    if max_drawdown_tolerance is None and max_drawdown_pct is not None:
        # Accept either fraction (0.10) or percent (10).
        mdd = float(max_drawdown_pct)
        max_drawdown_tolerance = mdd / 100.0 if mdd > 1.0 else mdd

    scen = (scenario or "balanced").strip().lower()
    if scen not in SCENARIOS:
        scen = "balanced"

    recommendations: List[Dict[str, Any]] = []
    stay_in_cash = False
    cash_reasons: List[str] = []

    if capital is None or float(capital) <= 0:
        stay_in_cash = True
        cash_reasons.append("capital_missing_or_nonpositive")
    if not data_trustworthy:
        stay_in_cash = True
        cash_reasons.append("data_not_trustworthy")
    if (liquidity_need or "").lower() == "high" and scen == "aggressive":
        stay_in_cash = True
        cash_reasons.append("high_liquidity_need_blocks_aggressive")
    if max_drawdown_tolerance is not None and float(max_drawdown_tolerance) < 0.03 and scen != "conservative":
        stay_in_cash = True
        cash_reasons.append("drawdown_tolerance_too_low_for_scenario")

    if stay_in_cash:
        recommendations.append(
            {
                "id": "stay_in_cash",
                "label": "Stay in Cash",
                "rationale": "; ".join(cash_reasons) or "Default to cash when inputs are weak.",
            }
        )
    else:
        priority = (income_growth_priority or "balanced").lower()
        if priority in ("income", "balanced"):
            comfort = (assignment_comfort or "medium").lower()
            if comfort == "low":
                recommendations.append(
                    {
                        "id": "shares_or_etf",
                        "label": "Shares / ETF allocation",
                        "rationale": "Low assignment comfort — prefer shares/ETF over short premium.",
                    }
                )
            else:
                recommendations.append(
                    {
                        "id": "wheel_csp_cc",
                        "label": "Wheel / CSP / CC research",
                        "rationale": "Income priority with assignment comfort allows Wheel path research.",
                    }
                )
        if priority in ("growth", "balanced"):
            recommendations.append(
                {
                    "id": "shares",
                    "label": "Shares",
                    "rationale": "Growth priority — equity shares within concentration limits.",
                }
            )
        if scen == "conservative" or (concentration_limit_pct is not None and float(concentration_limit_pct) < 0.15):
            recommendations.append(
                {
                    "id": "etf_hedge",
                    "label": "ETF allocation / hedge context",
                    "rationale": "Conservative or tight concentration — include ETF/hedge research.",
                }
            )
        if len(recommendations) > 1:
            recommendations.append(
                {
                    "id": "combination",
                    "label": "Combination (manual)",
                    "rationale": "Combine sleeves only after per-account risk check; no auto rebalance.",
                }
            )

    target_note = None
    if target_return_pct is not None:
        target_note = (
            f"Operator goal return {float(target_return_pct):.1f}% is a goal label only — "
            "not a forecast, guarantee, or promised outcome."
        )

    primary = recommendations[0]["label"] if recommendations else "Stay in Cash"
    return {
        "schema": "strategy_builder_r68",
        "inputs": {
            "capital": capital,
            "account": acct,
            "account_alias": acct,
            "horizon_days": horizon_days,
            "horizon_months": horizon_months,
            "income_growth_priority": income_growth_priority,
            "max_drawdown_tolerance": max_drawdown_tolerance,
            "max_drawdown_pct": max_drawdown_pct,
            "liquidity_need": liquidity_need,
            "assignment_comfort": assignment_comfort,
            "concentration_limit_pct": concentration_limit_pct,
            "target_return_pct": target_return_pct,
            "scenario": scen,
            "data_trustworthy": data_trustworthy,
        },
        "stay_in_cash": stay_in_cash,
        "cash_reasons": cash_reasons,
        "recommendations": recommendations,
        "primary_recommendation": primary,
        "return_guarantee": False,
        "target_return_honesty": target_note or "No target return supplied.",
        "promises_returns": False,
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "disclaimer": "Advisory plan only. Stay in Cash is valid. Never promises returns.",
    }
