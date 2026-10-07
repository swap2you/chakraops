# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R66 hedge scenario advisory — manual only; no auto execution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_hedge_scenarios(
    *,
    account_alias: str,
    portfolio_equity: Optional[float] = None,
    downside_move_pct: float = 0.10,
    hedge_etf: str = "SPY",
    put_premium_pct: float = 0.015,
    collar_call_credit_pct: float = 0.008,
    horizon_dte: int = 30,
) -> Dict[str, Any]:
    """Return explainable hedge research scenarios for one account.

    Costs are illustrative proxies from operator inputs — not live quotes.
    Never routes orders.
    """
    alias = (account_alias or "").strip() or "acct_individual"
    equity = float(portfolio_equity) if portfolio_equity is not None else None
    move = max(0.01, min(float(downside_move_pct), 0.50))
    dte = max(1, min(int(horizon_dte), 365))
    etf = (hedge_etf or "SPY").upper().strip()

    scenarios: List[Dict[str, Any]] = []

    scenarios.append(
        {
            "id": "etf_diversification_context",
            "title": "Broad ETF diversification context",
            "kind": "context",
            "assumptions": {"reference_etf": etf, "horizon_dte": dte},
            "explanation": (
                f"Compare concentration vs a broad index like {etf}. "
                "This is research context only — not a rebalance order."
            ),
            "auto_execute": False,
        }
    )

    if equity is not None and equity > 0:
        put_cost = equity * float(put_premium_pct)
        covered_downside = equity * move
        scenarios.append(
            {
                "id": "protective_put",
                "title": "Protective put (illustrative)",
                "kind": "protective_put",
                "assumptions": {
                    "portfolio_equity": equity,
                    "put_premium_pct": put_premium_pct,
                    "downside_move_pct": move,
                    "horizon_dte": dte,
                    "underlying": etf,
                    "quote_source": "operator_input_proxy",
                },
                "hedge_cost": round(put_cost, 2),
                "downside_coverage_notional": round(covered_downside, 2),
                "explanation": (
                    f"Illustrative put premium ~{put_premium_pct:.1%} of equity "
                    f"(${put_cost:,.0f}) for ~{move:.0%} downside coverage context. "
                    "Replace with live ORATS quotes before any manual ticket."
                ),
                "auto_execute": False,
            }
        )

        collar_net = equity * (float(put_premium_pct) - float(collar_call_credit_pct))
        scenarios.append(
            {
                "id": "collar",
                "title": "Collar (illustrative)",
                "kind": "collar",
                "assumptions": {
                    "portfolio_equity": equity,
                    "put_premium_pct": put_premium_pct,
                    "call_credit_pct": collar_call_credit_pct,
                    "horizon_dte": dte,
                    "underlying": etf,
                    "quote_source": "operator_input_proxy",
                },
                "hedge_cost": round(collar_net, 2),
                "explanation": (
                    "Collar nets put debit against short-call credit. "
                    "Caps upside; does not auto-execute."
                ),
                "auto_execute": False,
            }
        )

        index_hedge_notional = equity * move
        scenarios.append(
            {
                "id": "index_etf_hedge",
                "title": "Simple index/ETF hedge size context",
                "kind": "index_hedge",
                "assumptions": {
                    "portfolio_equity": equity,
                    "downside_move_pct": move,
                    "hedge_etf": etf,
                },
                "suggested_hedge_notional": round(index_hedge_notional, 2),
                "explanation": (
                    f"Rough notional to offset ~{move:.0%} portfolio move using {etf}. "
                    "Beta and liquidity must be verified manually."
                ),
                "auto_execute": False,
            }
        )
    else:
        scenarios.append(
            {
                "id": "missing_equity",
                "title": "Insufficient equity input",
                "kind": "blocked",
                "explanation": (
                    "Provide trustworthy portfolio_equity for this account only. "
                    "Do not invent balances or pool other accounts."
                ),
                "auto_execute": False,
            }
        )

    return {
        "schema": "hedge_advisory_v66",
        "account_alias": alias,
        "scenarios": scenarios,
        "event_assumptions": {
            "earnings_clusters": "operator_supplied_or_unavailable",
            "macro_events": "placeholder_until_trusted_calendar",
        },
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "auto_execute": False,
        "disclaimer": "Hedge scenarios are advisory research. Manual execution only.",
    }
