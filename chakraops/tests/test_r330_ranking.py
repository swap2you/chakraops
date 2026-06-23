"""R33.0 — deterministic ranking, tie-breaking, and top 5-7 limit."""
from datetime import datetime, timezone

from app.core.decision_engine.contract import (
    BULL,
    CSP,
    DecisionInput,
    OptionContract,
    PortfolioState,
)
from app.core.decision_engine.engine import evaluate
from app.core.decision_engine.profiles import get_profile

NOW = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat()
PF = PortfolioState(total_value=1_000_000.0, available_cash=600_000.0)


def _candidates():
    out = []
    for i in range(10):
        premium = round(1.0 + 0.2 * i, 4)
        out.append(
            DecisionInput(
                symbol=f"S{i}", strategy=CSP, market_regime=BULL, price=100.0, iv_rank=40.0,
                price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, sector="TECH",
                contract=OptionContract(delta=0.225, dte=33, premium=premium, strike=100.0,
                                        open_interest=1000, volume=200, bid_ask_spread_pct=0.0),
            )
        )
    return out


def test_top_limit_is_profile_max_recommendations():
    res = evaluate(_candidates(), profile_name="balanced", portfolio=PF, now=NOW)
    assert get_profile("balanced").max_recommendations == 7
    assert res["counts"]["actionable"] == 10
    assert len(res["actionable"]) == 7  # capped to top 7
    # overflow (3) lands in watch, not dropped silently.
    assert len(res["watch"]) == 3


def test_ranking_is_score_descending_with_ranks():
    res = evaluate(_candidates(), profile_name="balanced", portfolio=PF, now=NOW)
    ranked = res["actionable"]
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert [r["rank"] for r in ranked] == list(range(1, 8))


def test_tie_break_by_expected_dollars_then_symbol():
    res = evaluate(_candidates(), profile_name="balanced", portfolio=PF, now=NOW)
    ranked = res["actionable"]
    # S9 (premium 2.8) and S8 (2.6) both saturate score=100; S9 ranks first (more $).
    assert ranked[0]["symbol"] == "S9"
    assert ranked[1]["symbol"] == "S8"


def test_ranking_is_deterministic():
    a = evaluate(_candidates(), profile_name="balanced", portfolio=PF, now=NOW)
    b = evaluate(_candidates(), profile_name="balanced", portfolio=PF, now=NOW)
    assert [r["symbol"] for r in a["actionable"]] == [r["symbol"] for r in b["actionable"]]


def _conservative_candidates():
    out = []
    for i in range(10):
        out.append(
            DecisionInput(
                symbol=f"C{i}", strategy=CSP, market_regime=BULL, price=100.0, iv_rank=40.0,
                price_as_of=FRESH, chain_as_of=FRESH, earnings_days=30, sector="TECH",
                contract=OptionContract(delta=0.15, dte=37, premium=2.0, strike=100.0,
                                        open_interest=2000, volume=500, bid_ask_spread_pct=0.0),
            )
        )
    return out


def test_conservative_caps_to_five():
    assert get_profile("conservative").max_recommendations == 5
    res = evaluate(_conservative_candidates(), profile_name="conservative", portfolio=PF, now=NOW)
    assert res["counts"]["actionable"] == 10
    assert len(res["actionable"]) == 5  # capped to conservative top 5
    assert len(res["watch"]) == 5  # overflow preserved, not dropped
