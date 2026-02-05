from __future__ import annotations

from datetime import date, datetime

from app.signals.explain import SignalExplanation, build_explanations
from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, ScoreComponent, SignalScore
from app.signals.selection import SelectedSignal, SelectionConfig


def _make_scored(
    symbol: str,
    signal_type: SignalType,
    score_total: float,
    rank: int,
) -> ScoredSignalCandidate:
    """Helper to construct a minimal scored candidate for explanation tests."""
    cand = SignalCandidate(
        symbol=symbol,
        signal_type=signal_type,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=date(2026, 2, 20),
        strike=100.0,
        option_right="PUT" if signal_type == SignalType.CSP else "CALL",
        bid=1.0,
        ask=1.1,
        mid=None,
        volume=1000,
        open_interest=1000,
        delta=None,
        iv=None,
        annualized_yield=None,
        raw_yield=None,
        max_profit=None,
        collateral=None,
    )
    components = [
        ScoreComponent(name="premium_score", value=0.5, weight=1.0),
        ScoreComponent(name="dte_score", value=0.3, weight=1.0),
    ]
    return ScoredSignalCandidate(
        candidate=cand,
        score=SignalScore(total=score_total, components=components),
        rank=rank,
    )


def test_explanation_deterministic() -> None:
    """Explanations should be deterministic given the same inputs."""
    scored1 = _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1)
    scored2 = _make_scored("MSFT", SignalType.CC, score_total=0.8, rank=2)

    selected = [
        SelectedSignal(scored=scored1, selection_reason="SELECTED_BY_POLICY"),
        SelectedSignal(scored=scored2, selection_reason="SELECTED_BY_POLICY"),
    ]

    cfg = SelectionConfig(
        max_total=2,
        max_per_symbol=1,
        max_per_signal_type=None,
        min_score=0.0,
    )

    expl1 = build_explanations(selected, cfg)
    expl2 = build_explanations(selected, cfg)

    assert len(expl1) == len(expl2)
    assert [e.symbol for e in expl1] == [e.symbol for e in expl2]
    assert [e.total_score for e in expl1] == [e.total_score for e in expl2]
    assert [e.rank for e in expl1] == [e.rank for e in expl2]


def test_explanation_fields_correct() -> None:
    """Explanation fields should correctly reflect the selected signal."""
    scored = _make_scored("AAPL", SignalType.CSP, score_total=0.85, rank=1)
    selected = SelectedSignal(scored=scored, selection_reason="SELECTED_BY_POLICY")

    cfg = SelectionConfig(
        max_total=1,
        max_per_symbol=1,
        max_per_signal_type=1,
        min_score=0.5,
    )

    explanations = build_explanations([selected], cfg)
    assert len(explanations) == 1

    expl = explanations[0]
    assert expl.symbol == "AAPL"
    assert expl.signal_type == "CSP"
    assert expl.rank == 1
    assert expl.total_score == 0.85
    assert len(expl.score_components) == 2
    assert expl.selection_reason == "SELECTED_BY_POLICY"


def test_policy_snapshot_correctness() -> None:
    """Policy snapshot should match the selection config."""
    scored = _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1)
    selected = SelectedSignal(scored=scored, selection_reason="SELECTED_BY_POLICY")

    cfg = SelectionConfig(
        max_total=5,
        max_per_symbol=2,
        max_per_signal_type=3,
        min_score=0.7,
    )

    explanations = build_explanations([selected], cfg)
    assert len(explanations) == 1

    policy = explanations[0].policy_snapshot
    assert policy["max_total"] == 5
    assert policy["max_per_symbol"] == 2
    assert policy["max_per_signal_type"] == 3
    assert policy["min_score"] == 0.7


def test_explanations_preserve_order() -> None:
    """Explanations should preserve the order of selected signals."""
    scored_list = [
        _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1),
        _make_scored("MSFT", SignalType.CC, score_total=0.8, rank=2),
        _make_scored("GOOGL", SignalType.CSP, score_total=0.7, rank=3),
    ]

    selected = [
        SelectedSignal(scored=s, selection_reason="SELECTED_BY_POLICY")
        for s in scored_list
    ]

    cfg = SelectionConfig(
        max_total=10,
        max_per_symbol=10,
        max_per_signal_type=None,
        min_score=0.0,
    )

    explanations = build_explanations(selected, cfg)
    assert len(explanations) == 3
    assert [e.symbol for e in explanations] == ["AAPL", "MSFT", "GOOGL"]
    assert [e.rank for e in explanations] == [1, 2, 3]
