# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.1: CSP risk proxy — downside move estimate and loss proxy (advisory-first).

Deterministic: snapshot/symbol_context only; no wall-clock. Safe codes only.
"""

from __future__ import annotations

import math
from typing import Any, Dict

# Conservative default when no earnings/IV/ATR (deterministic)
DEFAULT_DOWNSIDE_MOVE_PCT = 7.0


def estimate_downside_move_pct(symbol_context: Dict[str, Any]) -> float:
    """
    Estimate conservative downside move % for CSP risk proxy.
    Prefer implied earnings move when earnings within N days (advisory);
    else ATR/IV proxy; else DEFAULT_DOWNSIDE_MOVE_PCT.
    Uses only snapshot/context fields (no wall-clock). Deterministic.
    """
    if not symbol_context:
        return DEFAULT_DOWNSIDE_MOVE_PCT

    # Earnings within N days: use implied move (advisory; do not block)
    earnings_days = symbol_context.get("earnings_days")
    if earnings_days is not None:
        try:
            days = int(earnings_days)
        except (TypeError, ValueError):
            days = 999
    else:
        days = 999

    earnings_days_threshold = int(symbol_context.get("earnings_days_for_move", 14))
    if days <= earnings_days_threshold:
        implied = symbol_context.get("implied_earnings_move_pct")
        if implied is not None:
            try:
                pct = float(implied)
                if pct > 0:
                    return min(25.0, max(1.0, pct))  # clamp 1–25%
            except (TypeError, ValueError):
                pass

    # ATR % proxy (e.g. 1–2 ATR move)
    atr_pct = symbol_context.get("atr_pct")
    if atr_pct is not None:
        try:
            pct = float(atr_pct)
            if pct > 0:
                # Use ~1.5 ATR as downside proxy
                return min(25.0, max(1.0, pct * 1.5))
        except (TypeError, ValueError):
            pass

    # IV proxy if available (e.g. 1 std move ≈ 0.4 * iv_pct for 1 month)
    iv_pct = symbol_context.get("iv_pct")
    if iv_pct is not None:
        try:
            pct = float(iv_pct)
            if pct > 0:
                return min(25.0, max(1.0, pct * 0.4))
        except (TypeError, ValueError):
            pass

    return DEFAULT_DOWNSIDE_MOVE_PCT


def estimate_csp_max_loss_proxy(
    strike: float,
    contracts: int,
    downside_move_pct: float,
) -> float:
    """
    Proxy max loss (do not net premium): (strike * downside_move_pct/100) * 100 * contracts.
    Conservative: gross downside notional move.
    """
    if strike <= 0 or contracts <= 0 or downside_move_pct <= 0:
        return 0.0
    move_per_share = strike * (downside_move_pct / 100.0)
    return move_per_share * 100.0 * contracts


def cap_contracts_by_risk_budget(
    risk_budget_usd: float,
    strike: float,
    downside_move_pct: float,
) -> int:
    """Max contracts such that estimate_csp_max_loss_proxy(strike, n, downside_move_pct) <= risk_budget_usd."""
    if risk_budget_usd <= 0 or strike <= 0 or downside_move_pct <= 0:
        return 0
    loss_per_contract = (strike * (downside_move_pct / 100.0)) * 100.0
    if loss_per_contract <= 0:
        return 0
    return max(0, int(math.floor(risk_budget_usd / loss_per_contract)))
