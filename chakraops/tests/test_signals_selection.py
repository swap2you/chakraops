from __future__ import annotations

from datetime import date, datetime

from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore
from app.signals.selection import (
    SelectedSignal,
    SelectionConfig,
    select_signals,
)


def _make_scored(
    symbol: str,
    signal_type: SignalType,
    score_total: float,
    rank: int,
) -> ScoredSignalCandidate:
    """Helper to construct a minimal scored candidate for selection tests."""
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
    return ScoredSignalCandidate(
        candidate=cand,
        score=SignalScore(total=score_total, components=[]),
        rank=rank,
    )


def test_selection_deterministic() -> None:
    """Selection should be deterministic given the same scored list and config."""
    scored = [
        _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1),
        _make_scored("AAPL", SignalType.CC, score_total=0.8, rank=2),
        _make_scored("MSFT", SignalType.CSP, score_total=0.7, rank=3),
    ]

    cfg = SelectionConfig(
        max_total=3,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=0.0,
    )

    sel1, _ = select_signals(scored, cfg)
    sel2, _ = select_signals(scored, cfg)

    assert [s.scored.candidate.symbol for s in sel1] == [
        s.scored.candidate.symbol for s in sel2
    ]
    assert [s.scored.rank for s in sel1] == [s.scored.rank for s in sel2]


def test_cap_enforcement() -> None:
    """Per-symbol, per-type, and total caps should be enforced."""
    scored = [
        _make_scored("AAPL", SignalType.CSP, 0.95, 1),
        _make_scored("AAPL", SignalType.CSP, 0.90, 2),
        _make_scored("AAPL", SignalType.CC, 0.85, 3),
        _make_scored("MSFT", SignalType.CSP, 0.80, 4),
        _make_scored("MSFT", SignalType.CC, 0.75, 5),
    ]

    cfg = SelectionConfig(
        max_total=3,
        max_per_symbol=2,
        max_per_signal_type=2,
        min_score=0.0,
    )

    selected, _ = select_signals(scored, cfg)

    # Total cap
    assert len(selected) <= cfg.max_total

    # Per-symbol cap
    counts_by_symbol = {}
    counts_by_type = {}
    for s in selected:
        sym = s.scored.candidate.symbol
        st = s.scored.candidate.signal_type
        counts_by_symbol[sym] = counts_by_symbol.get(sym, 0) + 1
        counts_by_type[st] = counts_by_type.get(st, 0) + 1

    assert all(c <= cfg.max_per_symbol for c in counts_by_symbol.values())
    assert all(c <= cfg.max_per_signal_type for c in counts_by_type.values())


def test_selection_reasons_present() -> None:
    """Selected signals should carry a non-empty selection_reason."""
    scored = [
        _make_scored("AAPL", SignalType.CSP, 0.9, 1),
        _make_scored("MSFT", SignalType.CSP, 0.8, 2),
    ]

    cfg = SelectionConfig(
        max_total=2,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=0.0,
    )

    selected, _ = select_signals(scored, cfg)
    assert selected
    for s in selected:
        assert isinstance(s, SelectedSignal)
        assert isinstance(s.selection_reason, str)
        assert s.selection_reason != ""


def test_selection_does_not_mutate_input() -> None:
    """Selection must not mutate or reorder the scored input list."""
    scored = [
        _make_scored("AAPL", SignalType.CSP, 0.9, 1),
        _make_scored("MSFT", SignalType.CC, 0.8, 2),
    ]
    original_ids = [id(s) for s in scored]

    cfg = SelectionConfig(
        max_total=1,
        max_per_symbol=1,
        max_per_signal_type=1,
        min_score=0.0,
    )

    selected, _ = select_signals(scored, cfg)

    # Ensure the original list and objects are unchanged
    assert [id(s) for s in scored] == original_ids
    assert [s.scored for s in selected] != []

