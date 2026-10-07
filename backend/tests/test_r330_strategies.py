"""R33.0 — strategy eligibility boundaries + stay-in-cash."""
from datetime import datetime, timezone

from app.core.decision_engine.contract import (
    BULL,
    COVERED_CALL,
    CSP,
    SHARE_BUY,
    DecisionInput,
    OptionContract,
    PortfolioState,
)
from app.core.decision_engine.engine import evaluate, evaluate_candidate
from app.core.decision_engine.profiles import get_profile
from app.core.decision_engine.strategies import evaluate_csp

NOW = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
BALANCED = get_profile("balanced")
PF = PortfolioState(total_value=100000.0, available_cash=60000.0)


def _csp(delta, dte, premium):
    return DecisionInput(
        symbol="AAA", strategy=CSP, market_regime=BULL, price=100.0, iv_rank=40.0,
        price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, sector="TECH",
        contract=OptionContract(delta=delta, dte=dte, premium=premium, strike=100.0,
                                open_interest=600, volume=100, bid_ask_spread_pct=2.0),
    )


def test_csp_delta_boundary_inside_and_outside():
    inside = evaluate_csp(_csp(0.30, 30, 2.0), BALANCED)  # 0.30 is inclusive max
    assert "DELTA_OUT_OF_RANGE" not in inside.soft_reasons
    outside = evaluate_csp(_csp(0.31, 30, 2.0), BALANCED)
    assert "DELTA_OUT_OF_RANGE" in outside.soft_reasons
    assert outside.passed_strategy_rules is False


def test_csp_dte_boundary():
    low = evaluate_csp(_csp(0.2, 20, 2.0), BALANCED)  # below 21
    assert "DTE_OUT_OF_RANGE" in low.soft_reasons
    ok = evaluate_csp(_csp(0.2, 21, 2.0), BALANCED)
    assert "DTE_OUT_OF_RANGE" not in ok.soft_reasons


def test_csp_below_return_threshold_goes_to_watch():
    inp = _csp(0.2, 30, 0.5)  # return 0.5% < 1.0% threshold
    out = evaluate_candidate(inp, BALANCED, portfolio=PF, now=NOW)
    assert out.decision_status == "WATCH"
    assert "BELOW_RETURN_THRESHOLD" in out.reason_codes


def test_covered_call_requires_holdings():
    inp = DecisionInput(
        symbol="BBB", strategy=COVERED_CALL, market_regime=BULL, price=100.0, iv_rank=40.0,
        price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, shares_held=50,
        contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=105.0,
                                open_interest=600, volume=100, bid_ask_spread_pct=2.0),
    )
    out = evaluate_candidate(inp, BALANCED, portfolio=PF, now=NOW)
    assert out.decision_status == "BLOCKED"
    assert "INSUFFICIENT_SHARES" in out.reason_codes


def test_share_buy_actionable():
    inp = DecisionInput(symbol="CCC", strategy=SHARE_BUY, market_regime=BULL,
                        price=100.0, iv_rank=30.0, price_as_of=FRESH, sector="TECH")
    out = evaluate_candidate(inp, BALANCED, portfolio=PF, now=NOW)
    assert out.decision_status == "ACTIONABLE"
    assert out.sizing["shares"] > 0
    assert out.expected_return_pct is None


def test_stay_in_cash_when_nothing_actionable():
    # Single below-threshold candidate -> no actionable -> explicit stay-in-cash.
    res = evaluate([_csp(0.2, 30, 0.5)], profile_name="balanced", portfolio=PF, now=NOW)
    assert res["counts"]["actionable"] == 0
    assert res["stay_in_cash"]["decision_status"] == "STAY_IN_CASH"
    assert res["stay_in_cash"]["reason_codes"] == ["NO_ACTIONABLE_CANDIDATES"]


def test_stay_in_cash_present_even_when_actionable():
    res = evaluate([_csp(0.225, 33, 2.5)], profile_name="balanced", portfolio=PF, now=NOW)
    assert res["counts"]["actionable"] == 1
    assert res["stay_in_cash"]["reason_codes"] == ["CASH_IS_FALLBACK_NOT_REQUIRED"]
