# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Independent expiry oracles. Expected dollars are fixtures, not a second copy of the formula."""

from __future__ import annotations

import math

from app.core.strategy.payoff_r68 import (
    calculate_credit_spread_payoff,
    calculate_short_put_payoff,
)


def test_csp_expiry_oracle_one_contract():
    # Standard 100-share $50 CSP sold for $1.50.
    result = calculate_short_put_payoff(
        strike=50,
        premium=1.50,
        contracts=1,
        underlying_prices=[45, 0],
    )
    assert result["max_profit"] == 150
    assert result["max_loss"] == 4850
    assert result["breakeven"] == 48.5
    assert result["curve"][0]["pnl"] == -350
    assert result["curve"][1]["pnl"] == -4850
    assert result["trade_execution"] is False


def test_credit_spread_expiry_oracle_five_wide():
    # $5-wide one-contract credit spread receiving $1.20.
    result = calculate_credit_spread_payoff(width=5, credit=1.20, contracts=1, short_strike=50, expiration_underlying=45)
    assert result["max_profit"] == 120
    assert result["max_loss"] == 380
    assert result["expiration_pnl"] == -380
    assert result["trade_execution"] is False


def test_non_finite_premium_waits():
    result = calculate_short_put_payoff(strike=50, premium=math.nan)
    assert result["decision"] == "WAIT"
    assert result["data_status"] == "DATA_UNAVAILABLE"
    assert "max_profit" not in result
