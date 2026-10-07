"""R33.0 — stale/missing-data integration: never act on bad data."""
from datetime import datetime, timedelta, timezone

from app.core.decision_engine.contract import (
    BULL,
    CSP,
    SHARE_BUY,
    DecisionInput,
    OptionContract,
    PortfolioState,
)
from app.core.decision_engine.engine import evaluate, evaluate_candidate
from app.core.decision_engine.profiles import get_profile

NOW = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
STALE = (NOW - timedelta(days=5)).isoformat()
BALANCED = get_profile("balanced")
PF = PortfolioState(total_value=100000.0, available_cash=60000.0)


def _csp(**kw):
    base = dict(symbol="AAA", strategy=CSP, market_regime=BULL, price=100.0, iv_rank=40.0,
                price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, sector="TECH",
                contract=OptionContract(delta=0.225, dte=33, premium=2.5, strike=100.0,
                                        open_interest=1000, volume=200, bid_ask_spread_pct=0.0))
    base.update(kw)
    return DecisionInput(**base)


def test_stale_chain_blocks_action():
    out = evaluate_candidate(_csp(chain_as_of=STALE), BALANCED, portfolio=PF, now=NOW)
    assert out.decision_status == "BLOCKED"
    assert out.data_quality == "BLOCKED"
    assert "STALE_OPTIONS_CHAIN" in out.reason_codes
    assert out.sizing == {}  # no sizing on blocked candidate


def test_missing_price_blocks_action():
    out = evaluate_candidate(_csp(price_as_of=None), BALANCED, portfolio=PF, now=NOW)
    assert out.decision_status == "BLOCKED"
    assert "MISSING_PRICE" in out.reason_codes


def test_missing_contract_blocks_action():
    out = evaluate_candidate(_csp(contract=None), BALANCED, portfolio=PF, now=NOW)
    assert out.decision_status == "BLOCKED"
    assert "MISSING_CONTRACT" in out.reason_codes


def test_no_actionable_from_all_stale_batch():
    res = evaluate([_csp(chain_as_of=STALE), _csp(symbol="BBB", price_as_of=None)],
                   profile_name="balanced", portfolio=PF, now=NOW)
    assert res["counts"]["actionable"] == 0
    assert res["counts"]["blocked"] == 2
    assert res["stay_in_cash"]["reason_codes"] == ["NO_ACTIONABLE_CANDIDATES"]


def test_share_buy_does_not_require_chain_freshness():
    # Share buy needs price but not options chain; stale/absent chain must not block it.
    inp = DecisionInput(symbol="CCC", strategy=SHARE_BUY, market_regime=BULL,
                        price=100.0, iv_rank=30.0, price_as_of=FRESH, chain_as_of=None, sector="TECH")
    out = evaluate_candidate(inp, BALANCED, portfolio=PF, now=NOW)
    assert out.decision_status == "ACTIONABLE"
