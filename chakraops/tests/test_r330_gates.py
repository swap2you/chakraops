"""R33.0 — eligibility and safety gates."""
from datetime import datetime, timedelta, timezone

from app.core.decision_engine import gates as G
from app.core.decision_engine.contract import (
    BEAR,
    BULL,
    COVERED_CALL,
    CSP,
    DecisionInput,
    OptionContract,
)
from app.core.decision_engine.profiles import get_profile

NOW = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
STALE = (NOW - timedelta(days=3)).isoformat()
BALANCED = get_profile("balanced")
CONSERVATIVE = get_profile("conservative")


def _csp(**kw):
    base = dict(symbol="AAA", strategy=CSP, market_regime=BULL, price=100.0,
                price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30,
                contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=100.0,
                                        open_interest=600, volume=100, bid_ask_spread_pct=2.0))
    base.update(kw)
    return DecisionInput(**base)


def test_freshness_blocks_stale_chain():
    res = G.check_data_freshness(_csp(chain_as_of=STALE), now=NOW)
    assert res.blocked is True
    assert "STALE_OPTIONS_CHAIN" in res.reason_codes


def test_freshness_blocks_missing_price():
    res = G.check_data_freshness(_csp(price_as_of=None), now=NOW)
    assert res.blocked is True
    assert "MISSING_PRICE" in res.reason_codes


def test_missing_critical_contract():
    ok, reasons = G.check_missing_critical(_csp(contract=None))
    assert ok is False
    assert "MISSING_CONTRACT" in reasons


def test_regime_gate():
    ok, r = G.regime_gate(_csp(market_regime=BEAR), CONSERVATIVE)
    assert ok is False and r == ["REGIME_EXCLUDED_BEAR"]
    ok, _ = G.regime_gate(_csp(market_regime=BULL), CONSERVATIVE)
    assert ok is True


def test_earnings_gate_blackout_and_unknown():
    ok, r = G.earnings_gate(_csp(earnings_days=2), BALANCED)
    assert ok is False and r == ["EARNINGS_BLACKOUT_2D"]
    ok, _ = G.earnings_gate(_csp(earnings_days=10), BALANCED)
    assert ok is True
    # Unknown earnings does not hard-block.
    ok, _ = G.earnings_gate(_csp(earnings_days=None), BALANCED)
    assert ok is True


def test_liquidity_gate():
    ok, _ = G.liquidity_gate(_csp(), BALANCED)
    assert ok is True
    bad = _csp(contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=100.0,
                                       open_interest=10, volume=1, bid_ask_spread_pct=20.0))
    ok, reasons = G.liquidity_gate(bad, BALANCED)
    assert ok is False
    assert "LOW_OPEN_INTEREST" in reasons and "WIDE_SPREAD" in reasons


def test_liquidity_data_missing():
    miss = _csp(contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=100.0))
    ok, reasons = G.liquidity_gate(miss, BALANCED)
    assert ok is False and reasons == ["LIQUIDITY_DATA_MISSING"]


def test_holdings_gate_for_covered_call():
    ok, r = G.holdings_gate(_csp(strategy=COVERED_CALL, shares_held=50))
    assert ok is False and r == ["INSUFFICIENT_SHARES"]
    ok, _ = G.holdings_gate(_csp(strategy=COVERED_CALL, shares_held=100))
    assert ok is True


def test_cash_gate_for_csp():
    ok, r = G.cash_gate(_csp(), BALANCED, available_cash_after_buffer=5000.0)
    assert ok is False and r == ["INSUFFICIENT_CASH"]  # one contract = 100*100 = 10000
    ok, _ = G.cash_gate(_csp(), BALANCED, available_cash_after_buffer=10000.0)
    assert ok is True
