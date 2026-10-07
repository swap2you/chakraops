"""R33.0 — position sizing and mandatory risk invariants."""
from datetime import datetime, timezone

import pytest

from app.core.decision_engine.contract import (
    BULL,
    COVERED_CALL,
    CSP,
    SHARE_BUY,
    DecisionInput,
    OptionContract,
    PortfolioState,
)
from app.core.decision_engine.profiles import get_profile
from app.core.decision_engine.sizing import (
    size_covered_call,
    size_csp,
    size_share_buy,
)

NOW = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
BALANCED = get_profile("balanced")


def _csp(strike=100.0):
    return DecisionInput(symbol="AAA", strategy=CSP, market_regime=BULL, price=strike,
                         price_as_of=FRESH, chain_as_of=FRESH, sector="TECH",
                         contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=strike,
                                                 open_interest=600, volume=100, bid_ask_spread_pct=2.0))


def test_no_uncovered_covered_call():
    inp = DecisionInput(symbol="BBB", strategy=COVERED_CALL, market_regime=BULL, price=100.0,
                        shares_held=150, contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=105.0))
    res = size_covered_call(inp, BALANCED, PortfolioState(total_value=100000.0, available_cash=0.0))
    assert res.sizing.contracts == 1  # 150 // 100 == 1, never 2
    assert res.sizing.contracts * 100 <= inp.shares_held
    assert res.capital_required == 0.0


def test_csp_never_reserves_more_than_available_after_buffer():
    # Buffer 20% of 100k = 20k -> after-buffer 30k; collateral 10k -> max 3, but
    # max_position 10% = 10k caps to 1 contract.
    pf = PortfolioState(total_value=100000.0, available_cash=50000.0)
    res = size_csp(_csp(), BALANCED, pf)
    assert res.sizing.contracts == 1
    assert res.capital_required <= pf.available_cash
    assert res.capital_required == 10000.0


def test_csp_zero_when_cash_too_small():
    pf = PortfolioState(total_value=12000.0, available_cash=11000.0)
    # buffer 20% of 12k = 2400 -> after-buffer 8600 < 10k collateral -> 0 contracts.
    res = size_csp(_csp(), BALANCED, pf)
    assert res.sizing.contracts == 0
    assert res.capital_required == 0.0
    assert "CASH_INSUFFICIENT_FOR_ONE_CONTRACT" in res.risk_flags


def test_no_negative_quantities():
    pf = PortfolioState(total_value=0.0, available_cash=0.0)
    assert size_csp(_csp(), BALANCED, pf).sizing.contracts == 0
    assert size_share_buy(
        DecisionInput(symbol="C", strategy=SHARE_BUY, market_regime=BULL, price=100.0, sector="X"),
        BALANCED, pf,
    ).sizing.shares == 0


def test_share_buy_respects_buffer_and_caps():
    pf = PortfolioState(total_value=100000.0, available_cash=60000.0)
    inp = DecisionInput(symbol="C", strategy=SHARE_BUY, market_regime=BULL, price=100.0, sector="TECH")
    res = size_share_buy(inp, BALANCED, pf)
    # max_position 10% = 10k -> 100 shares.
    assert res.sizing.shares == 100
    assert res.capital_required <= pf.available_cash


def test_symbol_exposure_headroom_limits_sizing():
    pf = PortfolioState(total_value=100000.0, available_cash=60000.0,
                        symbol_exposure={"AAA": 19000.0})  # symbol cap 20% = 20k, headroom 1k
    res = size_csp(_csp(), BALANCED, pf)
    assert res.sizing.contracts == 0  # headroom 1k < 10k collateral
