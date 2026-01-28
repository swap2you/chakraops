from __future__ import annotations

from datetime import date, datetime, timedelta

from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import (
    ScoredSignalCandidate,
    ScoringConfig,
    score_signals,
)


def _make_candidate(
    symbol: str,
    signal_type: SignalType,
    underlying_price: float,
    expiry: date,
    strike: float,
    bid: float,
    ask: float,
    open_interest: int,
) -> SignalCandidate:
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    return SignalCandidate(
        symbol=symbol,
        signal_type=signal_type,
        as_of=as_of,
        underlying_price=underlying_price,
        expiry=expiry,
        strike=strike,
        option_right="PUT" if signal_type == SignalType.CSP else "CALL",
        bid=bid,
        ask=ask,
        mid=None,  # let scoring compute from bid/ask
        volume=1000,
        open_interest=open_interest,
        delta=None,
        iv=None,
        annualized_yield=None,
        raw_yield=None,
        max_profit=None,
        collateral=None,
    )


def _default_config() -> ScoringConfig:
    return ScoringConfig(
        premium_weight=1.0,
        dte_weight=1.0,
        spread_weight=1.0,
        otm_weight=1.0,
        liquidity_weight=1.0,
    )


def test_score_deterministic() -> None:
    """Scoring the same candidates twice should produce identical scores and ranks."""
    base_date = date(2026, 2, 20)
    candidates = [
        _make_candidate(
            symbol="AAPL",
            signal_type=SignalType.CSP,
            underlying_price=150.0,
            expiry=base_date,
            strike=145.0,
            bid=2.5,
            ask=2.6,
            open_interest=5000,
        ),
        _make_candidate(
            symbol="AAPL",
            signal_type=SignalType.CC,
            underlying_price=150.0,
            expiry=base_date + timedelta(days=10),
            strike=155.0,
            bid=3.0,
            ask=3.2,
            open_interest=4000,
        ),
    ]

    config = _default_config()

    scored1 = score_signals(candidates, config)
    scored2 = score_signals(candidates, config)

    assert [s.score.total for s in scored1] == [s.score.total for s in scored2]
    assert [s.rank for s in scored1] == [s.rank for s in scored2]
    # Ensure order is deterministic
    assert [s.candidate.symbol for s in scored1] == [s.candidate.symbol for s in scored2]


def test_rank_assignment() -> None:
    """Ranks should be 1..N in descending score order."""
    base_date = date(2026, 2, 20)
    candidates = [
        _make_candidate(
            symbol="AAPL",
            signal_type=SignalType.CSP,
            underlying_price=150.0,
            expiry=base_date,
            strike=140.0,
            bid=2.5,
            ask=2.6,
            open_interest=3000,
        ),
        _make_candidate(
            symbol="MSFT",
            signal_type=SignalType.CSP,
            underlying_price=400.0,
            expiry=base_date + timedelta(days=5),
            strike=390.0,
            bid=4.0,
            ask=4.2,
            open_interest=8000,
        ),
        _make_candidate(
            symbol="GOOGL",
            signal_type=SignalType.CC,
            underlying_price=200.0,
            expiry=base_date + timedelta(days=10),
            strike=210.0,
            bid=1.0,
            ask=1.1,
            open_interest=1000,
        ),
    ]

    config = _default_config()
    scored = score_signals(candidates, config)

    assert [s.rank for s in scored] == list(range(1, len(scored) + 1))

    # Scores must be non-increasing with rank
    totals = [s.score.total for s in scored]
    assert totals == sorted(totals, reverse=True)


def test_weight_effect() -> None:
    """Changing a component weight should be able to change ordering."""
    base_date = date(2026, 2, 20)
    # Candidate A: higher premium, lower liquidity
    cand_a = _make_candidate(
        symbol="AAPL",
        signal_type=SignalType.CSP,
        underlying_price=150.0,
        expiry=base_date,
        strike=145.0,
        bid=3.0,
        ask=3.2,
        open_interest=1000,
    )
    # Candidate B: lower premium, higher liquidity
    cand_b = _make_candidate(
        symbol="MSFT",
        signal_type=SignalType.CSP,
        underlying_price=300.0,
        expiry=base_date,
        strike=290.0,
        bid=1.0,
        ask=1.1,
        open_interest=10000,
    )
    candidates = [cand_a, cand_b]

    # Emphasize premium
    config_premium = ScoringConfig(
        premium_weight=1.0,
        dte_weight=0.0,
        spread_weight=0.0,
        otm_weight=0.0,
        liquidity_weight=0.0,
    )
    scored_premium = score_signals(candidates, config_premium)
    top_symbol_premium = scored_premium[0].candidate.symbol

    # Emphasize liquidity
    config_liquidity = ScoringConfig(
        premium_weight=0.0,
        dte_weight=0.0,
        spread_weight=0.0,
        otm_weight=0.0,
        liquidity_weight=1.0,
    )
    scored_liquidity = score_signals(candidates, config_liquidity)
    top_symbol_liquidity = scored_liquidity[0].candidate.symbol

    # With premium emphasis, higher-premium candidate should win
    assert top_symbol_premium == "AAPL"
    # With liquidity emphasis, higher-liquidity candidate should win
    assert top_symbol_liquidity == "MSFT"


def test_no_mutation_of_candidates() -> None:
    """Scoring must not mutate or reorder the original candidate list."""
    base_date = date(2026, 2, 20)
    original = [
        _make_candidate(
            symbol="AAPL",
            signal_type=SignalType.CSP,
            underlying_price=150.0,
            expiry=base_date,
            strike=145.0,
            bid=2.5,
            ask=2.6,
            open_interest=5000,
        ),
        _make_candidate(
            symbol="MSFT",
            signal_type=SignalType.CC,
            underlying_price=400.0,
            expiry=base_date + timedelta(days=10),
            strike=410.0,
            bid=3.0,
            ask=3.2,
            open_interest=3000,
        ),
    ]
    # Make a shallow copy to check ordering
    candidates = list(original)

    config = _default_config()
    scored = score_signals(candidates, config)

    # Original list order and objects must be unchanged
    assert candidates == original
    assert all(isinstance(s, ScoredSignalCandidate) for s in scored)
    assert [id(c) for c in candidates] == [id(o) for o in original]

