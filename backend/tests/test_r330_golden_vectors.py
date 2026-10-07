"""R33.0 — golden calculation vectors.

Hand-computed expected values for the documented deterministic scoring and
sizing formulas. If a formula changes, these must be updated intentionally.

Option score = 0.40*return + 0.25*delta + 0.15*dte + 0.20*liquidity.
"""
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
from app.core.decision_engine.engine import evaluate_candidate
from app.core.decision_engine.profiles import get_profile
from app.core.decision_engine.strategies import (
    evaluate_csp,
    evaluate_covered_call,
    evaluate_share_buy,
)

NOW = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
BALANCED = get_profile("balanced")


def _csp(delta, dte, premium, strike, oi, spread):
    return DecisionInput(
        symbol="AAA", strategy=CSP, market_regime=BULL, price=strike, iv_rank=40.0,
        price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, sector="TECH",
        contract=OptionContract(delta=delta, dte=dte, premium=premium, strike=strike,
                                open_interest=oi, volume=200, bid_ask_spread_pct=spread),
    )


def test_gv1_perfect_csp_scores_100():
    seval = evaluate_csp(_csp(0.225, 33, 2.5, 100.0, 1000, 0.0), BALANCED)
    assert seval.return_pct == 2.5
    assert seval.score == 100.0
    assert seval.passed_strategy_rules is True


def test_gv2_edge_csp_scores_38_5():
    # delta edge 0.30, dte edge 45, return == threshold, oi == min, spread == max.
    seval = evaluate_csp(_csp(0.30, 45, 1.0, 100.0, 250, 8.0), BALANCED)
    assert seval.return_pct == 1.0
    assert seval.score == 38.5
    assert seval.passed_strategy_rules is True  # all soft rules met, just low score


def test_gv3_covered_call_return_uses_price():
    inp = DecisionInput(
        symbol="BBB", strategy=COVERED_CALL, market_regime=BULL, price=50.0, iv_rank=40.0,
        price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, shares_held=300, sector="TECH",
        contract=OptionContract(delta=0.225, dte=33, premium=1.5, strike=52.0,
                                open_interest=1000, volume=200, bid_ask_spread_pct=0.0),
    )
    seval = evaluate_covered_call(inp, BALANCED)
    assert seval.return_pct == 3.0  # 1.5 / 50 * 100
    assert seval.score == 100.0


def test_gv4_share_buy_score():
    inp = DecisionInput(symbol="CCC", strategy=SHARE_BUY, market_regime=BULL,
                        price=100.0, iv_rank=30.0, price_as_of=FRESH)
    seval = evaluate_share_buy(inp, BALANCED)
    # 0.6*(100-30) + 0.4*100 = 42 + 40 = 82
    assert seval.score == 82.0


def test_gv_csp_sizing_and_capital():
    pf = PortfolioState(total_value=100000.0, available_cash=60000.0)
    out = evaluate_candidate(_csp(0.225, 33, 2.5, 100.0, 1000, 0.0), BALANCED, portfolio=pf, now=NOW)
    # buffer 20% of 100k = 20k -> after-buffer 40k; max_position 10% = 10k; 1 contract.
    assert out.sizing["contracts"] == 1
    assert out.capital_required == 10000.0
    assert out.expected_return_dollars == 250.0  # 2.5 * 100 * 1
    assert out.expected_return_pct == 2.5
    assert out.decision_status == "ACTIONABLE"


def test_gv_covered_call_sizing_no_capital():
    pf = PortfolioState(total_value=100000.0, available_cash=60000.0)
    inp = DecisionInput(
        symbol="BBB", strategy=COVERED_CALL, market_regime=BULL, price=50.0, iv_rank=40.0,
        price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, shares_held=300, sector="TECH",
        contract=OptionContract(delta=0.225, dte=33, premium=1.5, strike=52.0,
                                open_interest=1000, volume=200, bid_ask_spread_pct=0.0),
    )
    out = evaluate_candidate(inp, BALANCED, portfolio=pf, now=NOW)
    assert out.sizing["contracts"] == 3  # 300 // 100
    assert out.capital_required == 0.0
    assert out.expected_return_dollars == 450.0  # 1.5 * 100 * 3
