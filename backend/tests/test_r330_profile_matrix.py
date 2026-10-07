"""R33.0 — profile comparison matrix.

The same candidate routed through different profiles must yield documented,
different outcomes (regime/earnings tolerance, delta range, scoring).
"""
from datetime import datetime, timezone

from app.core.decision_engine.contract import (
    BULL,
    CSP,
    DecisionInput,
    OptionContract,
    PortfolioState,
)
from app.core.decision_engine.engine import evaluate_candidate
from app.core.decision_engine.profiles import get_profile

NOW = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
PF = PortfolioState(total_value=100000.0, available_cash=60000.0)


def _candidate(delta=0.28, earnings_days=5):
    return DecisionInput(
        symbol="AAA", strategy=CSP, market_regime=BULL, price=100.0, iv_rank=40.0,
        price_as_of=FRESH, chain_as_of=FRESH, earnings_days=earnings_days, sector="TECH",
        contract=OptionContract(delta=delta, dte=30, premium=2.0, strike=100.0,
                                open_interest=600, volume=100, bid_ask_spread_pct=2.0),
    )


def test_earnings_blackout_differs_by_profile():
    cand = _candidate(earnings_days=5)
    cons = evaluate_candidate(cand, get_profile("conservative"), portfolio=PF, now=NOW)
    bal = evaluate_candidate(cand, get_profile("balanced"), portfolio=PF, now=NOW)
    agg = evaluate_candidate(cand, get_profile("aggressive"), portfolio=PF, now=NOW)
    # Conservative blackout 7d blocks; balanced (3d) and aggressive (0d) do not.
    assert cons.decision_status == "BLOCKED"
    assert any("EARNINGS_BLACKOUT" in r for r in cons.reason_codes)
    assert bal.decision_status != "BLOCKED"
    assert agg.decision_status != "BLOCKED"


def test_delta_range_differs_by_profile():
    cand = _candidate(delta=0.28, earnings_days=30)
    cons = evaluate_candidate(cand, get_profile("conservative"), portfolio=PF, now=NOW)
    bal = evaluate_candidate(cand, get_profile("balanced"), portfolio=PF, now=NOW)
    agg = evaluate_candidate(cand, get_profile("aggressive"), portfolio=PF, now=NOW)
    # 0.28 is outside conservative [0.10,0.20] -> WATCH; inside balanced/aggressive.
    assert cons.decision_status == "WATCH"
    assert "DELTA_OUT_OF_RANGE" in cons.reason_codes
    assert bal.decision_status == "ACTIONABLE"
    assert agg.decision_status == "ACTIONABLE"


def test_scores_differ_across_profiles():
    cand = _candidate(delta=0.28, earnings_days=30)
    bal = evaluate_candidate(cand, get_profile("balanced"), portfolio=PF, now=NOW)
    agg = evaluate_candidate(cand, get_profile("aggressive"), portfolio=PF, now=NOW)
    # Aggressive's lower return threshold + wider liquidity raises the score.
    assert agg.score > bal.score


def test_aggressive_sizes_larger_than_balanced():
    cand = _candidate(delta=0.28, earnings_days=30)
    bal = evaluate_candidate(cand, get_profile("balanced"), portfolio=PF, now=NOW)
    agg = evaluate_candidate(cand, get_profile("aggressive"), portfolio=PF, now=NOW)
    # Smaller cash buffer + higher allocation cap -> more contracts.
    assert agg.sizing["contracts"] >= bal.sizing["contracts"]
