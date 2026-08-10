# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R44 — consolidated Wheel/Portfolio finance invariants.

CSP collateral = strike × 100 × contracts; premium dollars = premium × 100 × contracts;
breakeven math; CC requires 100 shares/contract; zero cash stays zero (≠ total capital).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.decision_engine.contract import (
    BULL,
    COVERED_CALL,
    CSP,
    DecisionInput,
    OptionContract,
    PortfolioState,
)
from app.core.decision_engine.engine import evaluate_candidate
from app.core.decision_engine.profiles import get_profile
from app.core.decision_engine.sizing import size_covered_call
from app.core.decision_engine.wheel_v2.manual_plan import build_manual_plan

NOW = datetime(2026, 8, 10, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
BALANCED = get_profile("balanced")


def test_csp_collateral_is_strike_times_100_times_contracts() -> None:
    plan = build_manual_plan(strategy="CSP", strike=95.0, premium=1.25, contracts=3)
    assert plan.collateral == 95.0 * 100 * 3
    assert plan.breakeven == pytest.approx(95.0 - 1.25)


def test_csp_premium_times_100_expected_return_dollars() -> None:
    inp = DecisionInput(
        symbol="AAA",
        strategy=CSP,
        market_regime=BULL,
        price=100.0,
        price_as_of=FRESH,
        chain_as_of=FRESH,
        sector="TECH",
        contract=OptionContract(
            delta=0.25,
            dte=30,
            premium=2.5,
            strike=100.0,
            open_interest=600,
            volume=100,
            bid_ask_spread_pct=2.0,
        ),
    )
    out = evaluate_candidate(inp, BALANCED, portfolio=PortfolioState(total_value=100000.0, available_cash=50000.0), now=NOW)
    contracts = out.sizing["contracts"] if isinstance(out.sizing, dict) else (out.sizing.contracts or 1)
    assert out.expected_return_dollars == pytest.approx(2.5 * 100 * contracts)


def test_cc_requires_100_shares_per_contract() -> None:
    inp = DecisionInput(
        symbol="BBB",
        strategy=COVERED_CALL,
        market_regime=BULL,
        price=100.0,
        shares_held=250,
        contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=105.0),
    )
    res = size_covered_call(inp, BALANCED, PortfolioState(total_value=100000.0, available_cash=0.0))
    assert res.sizing.contracts == 2  # 250 // 100
    assert (res.sizing.contracts or 0) * 100 <= inp.shares_held


def test_cc_zero_shares_sizes_to_zero() -> None:
    inp = DecisionInput(
        symbol="CCC",
        strategy=COVERED_CALL,
        market_regime=BULL,
        price=100.0,
        shares_held=0,
        contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=105.0),
    )
    res = size_covered_call(inp, BALANCED, PortfolioState(total_value=100000.0, available_cash=50000.0))
    assert (res.sizing.contracts or 0) == 0


def test_zero_cash_stays_zero_not_total_capital(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.wheel_v2_routes import _portfolio_from_account

    monkeypatch.setattr(
        "app.core.accounts.holdings_db.get_account_summary",
        lambda account_id=None: {
            "account_id": account_id or "default",
            "cash": 0.0,
            "buying_power": 40000.0,
            "balances_present": True,
            "balances_updated_at": "2026-08-10T00:00:00Z",
        },
    )
    port = _portfolio_from_account(SimpleNamespace(account_id="default", total_capital=250000.0))
    assert port["cash"] == 0.0
    assert port["available_cash"] == 0.0
    assert port["total_capital"] == 250000.0
    assert port["buying_power"] == 40000.0
    assert port["available_cash"] != port["total_capital"]
    assert port["buying_power"] != port["available_cash"] or port["available_cash"] == 0.0
