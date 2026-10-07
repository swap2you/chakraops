# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R68 simple payoff / breakeven calculator for visual options lab."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _unavailable(strategy: str) -> Dict[str, Any]:
    return {
        "strategy": strategy,
        "ok": False,
        "data_status": "DATA_UNAVAILABLE",
        "decision": "WAIT",
        "manual_only": True,
        "trade_execution": False,
    }


def calculate_credit_spread_payoff(
    *,
    width: float,
    credit: float,
    contracts: int = 1,
    short_strike: Optional[float] = None,
    expiration_underlying: Optional[float] = None,
) -> Dict[str, Any]:
    """Expiry payoff for one defined-risk credit spread.

    ``credit`` and ``width`` are per share. One standard contract covers 100 shares.
    Maximum gain is the credit. Maximum loss is width minus credit, times the multiplier.
    """
    if not _finite(width) or not _finite(credit) or int(contracts) < 1 or float(width) <= 0 or float(credit) < 0:
        return _unavailable("credit_spread")
    if float(credit) >= float(width):
        return _unavailable("credit_spread")
    n = int(contracts)
    mult = 100 * n
    max_profit = float(credit) * mult
    max_loss = (float(width) - float(credit)) * mult
    out: Dict[str, Any] = {
        "strategy": "credit_spread",
        "width": float(width),
        "credit": float(credit),
        "contracts": n,
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "bounded_max_profit": True,
        "bounded_max_loss": True,
        "manual_only": True,
        "trade_execution": False,
    }
    if expiration_underlying is not None and short_strike is not None:
        if not _finite(expiration_underlying) or not _finite(short_strike):
            return _unavailable("credit_spread")
        # Bull put spread: short strike above the long strike by ``width``.
        intrinsic = max(float(short_strike) - float(expiration_underlying), 0.0)
        spread_intrinsic = min(intrinsic, float(width))
        out["expiration_pnl"] = round(max_profit - spread_intrinsic * mult, 2)
    return out


def calculate_short_put_payoff(
    *,
    strike: float,
    premium: float,
    contracts: int = 1,
    underlying_prices: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Cash-secured put payoff curve (per contract × 100 shares).

    Max profit is premium received (bounded). Max loss theoretically to zero
    underlying (bounded by strike * 100 * contracts - premium).
    """
    if not _finite(strike) or not _finite(premium) or int(contracts) < 1 or float(premium) < 0 or float(strike) <= 0:
        return _unavailable("short_put")
    k = float(strike)
    p = float(premium)
    n = max(1, int(contracts))
    mult = 100 * n
    credit = p * mult
    max_profit = credit
    max_loss = k * mult - credit
    breakeven = k - p

    prices = underlying_prices
    if not prices:
        # Sample around strike
        step = max(k * 0.05, 1.0)
        prices = [max(0.0, k + i * step) for i in range(-4, 5)]

    curve: List[Dict[str, float]] = []
    for px in prices:
        # Short put P/L at expiration
        intrinsic = max(k - float(px), 0.0) * mult
        pnl = credit - intrinsic
        curve.append({"underlying": float(px), "pnl": round(pnl, 2)})

    return {
        "strategy": "short_put",
        "strike": k,
        "premium": p,
        "contracts": n,
        "breakeven": round(breakeven, 4),
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "collateral": round(k * mult, 2),
        "curve": curve,
        "bounded_max_profit": True,
        "bounded_max_loss": True,
        "manual_only": True,
        "trade_execution": False,
    }


def calculate_covered_call_payoff(
    *,
    shares_cost_basis: float,
    call_strike: float,
    call_premium: float,
    shares: int = 100,
    underlying_prices: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Covered call payoff at expiration (long shares + short call)."""
    basis = float(shares_cost_basis)
    k = float(call_strike)
    p = float(call_premium)
    sh = max(1, int(shares))
    credit = p * sh  # premium per share * shares (options: 1 contract ≈ 100 sh)
    # Normalize: if shares==100, treat premium as per-share option premium
    max_profit = (k - basis) * sh + credit
    # Max loss if shares → 0: -basis*sh + credit
    max_loss = basis * sh - credit
    breakeven = basis - p

    prices = underlying_prices
    if not prices:
        step = max(k * 0.05, 1.0)
        prices = [max(0.0, k + i * step) for i in range(-4, 5)]

    curve: List[Dict[str, float]] = []
    for px in prices:
        stock_pnl = (float(px) - basis) * sh
        call_pnl = credit - max(float(px) - k, 0.0) * sh
        curve.append({"underlying": float(px), "pnl": round(stock_pnl + call_pnl, 2)})

    return {
        "strategy": "covered_call",
        "shares_cost_basis": basis,
        "call_strike": k,
        "call_premium": p,
        "shares": sh,
        "breakeven": round(breakeven, 4),
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "curve": curve,
        "bounded_max_profit": True,
        "bounded_max_loss": False,
        "manual_only": True,
        "trade_execution": False,
    }


def calculate_payoff(
    strategy: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Dispatch payoff calculator by strategy name."""
    name = (strategy or "").strip().lower()
    if name in ("short_put", "csp", "cash_secured_put"):
        return calculate_short_put_payoff(
            strike=float(kwargs["strike"]),
            premium=float(kwargs["premium"]),
            contracts=int(kwargs.get("contracts") or 1),
            underlying_prices=kwargs.get("underlying_prices"),
        )
    if name in ("covered_call", "cc"):
        return calculate_covered_call_payoff(
            shares_cost_basis=float(kwargs["shares_cost_basis"]),
            call_strike=float(kwargs["call_strike"]),
            call_premium=float(kwargs["call_premium"]),
            shares=int(kwargs.get("shares") or 100),
            underlying_prices=kwargs.get("underlying_prices"),
        )
    return {
        "ok": False,
        "error": "unsupported_strategy",
        "supported": ["short_put", "covered_call"],
        "manual_only": True,
        "trade_execution": False,
    }
