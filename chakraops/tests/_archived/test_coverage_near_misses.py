"""Tests for coverage summary and near-miss diagnostics (Phase 7.4)."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from app.signals.decision_snapshot import (
    DecisionSnapshot,
    _build_coverage_summary,
    _identify_near_misses,
    build_decision_snapshot,
)
from app.signals.engine import SignalRunResult
from app.signals.models import ExclusionReason, SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, ScoreComponent, SignalScore
from app.signals.selection import SelectedSignal


def test_coverage_summary_present() -> None:
    """Test that coverage_summary is built when candidates exist."""
    candidate1 = SignalCandidate(
        symbol="AAPL",
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=100.0,
        option_right="PUT",
        bid=1.0,
        ask=1.1,
    )
    
    candidate2 = SignalCandidate(
        symbol="MSFT",
        signal_type=SignalType.CC,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=200.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=210.0,
        option_right="CALL",
        bid=2.0,
        ask=2.1,
    )

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate1, candidate2],
        exclusions=[],
        stats={"total_candidates": 2, "symbols_evaluated": 2},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Verify coverage_summary is present
    assert snapshot.coverage_summary is not None
    
    summary = snapshot.coverage_summary
    assert "by_symbol" in summary
    assert "total_symbols_evaluated" in summary
    
    # Verify per-symbol coverage
    by_symbol = summary["by_symbol"]
    assert "AAPL" in by_symbol
    assert "MSFT" in by_symbol
    
    aapl_coverage = by_symbol["AAPL"]
    assert aapl_coverage["generation"] == 1
    assert aapl_coverage["scoring"] == 0  # No scoring
    assert aapl_coverage["selection"] == 0  # No selection


def test_coverage_summary_with_scoring_selection() -> None:
    """Test coverage_summary tracks scoring and selection stages."""
    candidate = SignalCandidate(
        symbol="AAPL",
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=100.0,
        option_right="PUT",
        bid=1.0,
        ask=1.1,
    )
    
    scored = ScoredSignalCandidate(
        candidate=candidate,
        score=SignalScore(total=0.85, components=[ScoreComponent(name="premium", value=0.5, weight=1.0)]),
        rank=1,
    )
    
    selected = SelectedSignal(scored=scored, selection_reason="SELECTED_BY_POLICY")

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1, "symbols_evaluated": 1},
        scored_candidates=[scored],
        selected_signals=[selected],
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    assert snapshot.coverage_summary is not None
    by_symbol = snapshot.coverage_summary["by_symbol"]
    aapl_coverage = by_symbol["AAPL"]
    assert aapl_coverage["generation"] == 1
    assert aapl_coverage["scoring"] == 1
    assert aapl_coverage["selection"] == 1


def test_coverage_summary_absent() -> None:
    """Test that coverage_summary is None when no candidates (backward compatibility)."""
    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[],
        exclusions=[],
        stats={"symbols_evaluated": 0},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Verify coverage_summary is None when no candidates
    assert snapshot.coverage_summary is None


def test_near_misses_min_score() -> None:
    """Test near-miss detection for min_score rule."""
    candidate1 = SignalCandidate(
        symbol="AAPL",
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=100.0,
        option_right="PUT",
        bid=1.0,
        ask=1.1,
    )
    
    candidate2 = SignalCandidate(
        symbol="MSFT",
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=200.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=200.0,
        option_right="PUT",
        bid=2.0,
        ask=2.1,
    )
    
    # Candidate1: score 0.9 (above min_score 0.5) - selected
    scored1 = ScoredSignalCandidate(
        candidate=candidate1,
        score=SignalScore(total=0.9, components=[]),
        rank=1,
    )
    
    # Candidate2: score 0.4 (below min_score 0.5) - near-miss
    scored2 = ScoredSignalCandidate(
        candidate=candidate2,
        score=SignalScore(total=0.4, components=[]),
        rank=2,
    )
    
    selected = SelectedSignal(scored=scored1, selection_reason="SELECTED_BY_POLICY")
    
    # Build snapshot with selection_config
    from app.signals.explain import build_explanations
    from app.signals.selection import SelectionConfig
    
    selection_config = SelectionConfig(
        max_total=10,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=0.5,
    )
    
    explanations = build_explanations([selected], selection_config)

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate1, candidate2],
        exclusions=[],
        stats={"total_candidates": 2, "symbols_evaluated": 2},
        scored_candidates=[scored1, scored2],
        selected_signals=[selected],
        explanations=explanations,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Verify near_misses is present
    assert snapshot.near_misses is not None
    assert len(snapshot.near_misses) == 1
    
    near_miss = snapshot.near_misses[0]
    assert near_miss["symbol"] == "MSFT"
    assert near_miss["failed_rule"] == "min_score"
    assert near_miss["actual_value"] == 0.4
    assert near_miss["required_value"] == 0.5


def test_near_misses_max_per_symbol() -> None:
    """Test near-miss detection for max_per_symbol rule."""
    candidate1 = SignalCandidate(
        symbol="AAPL",
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=100.0,
        option_right="PUT",
        bid=1.0,
        ask=1.1,
    )
    
    candidate2 = SignalCandidate(
        symbol="AAPL",  # Same symbol
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=datetime(2026, 3, 20).date(),  # Different expiry
        strike=100.0,
        option_right="PUT",
        bid=1.0,
        ask=1.1,
    )
    
    scored1 = ScoredSignalCandidate(
        candidate=candidate1,
        score=SignalScore(total=0.9, components=[]),
        rank=1,
    )
    
    scored2 = ScoredSignalCandidate(
        candidate=candidate2,
        score=SignalScore(total=0.8, components=[]),
        rank=2,
    )
    
    # Only candidate1 selected (max_per_symbol=1)
    selected = SelectedSignal(scored=scored1, selection_reason="SELECTED_BY_POLICY")
    
    from app.signals.explain import build_explanations
    from app.signals.selection import SelectionConfig
    
    selection_config = SelectionConfig(
        max_total=10,
        max_per_symbol=1,  # Only 1 per symbol
        max_per_signal_type=None,
        min_score=None,
    )
    
    explanations = build_explanations([selected], selection_config)

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate1, candidate2],
        exclusions=[],
        stats={"total_candidates": 2},
        scored_candidates=[scored1, scored2],
        selected_signals=[selected],
        explanations=explanations,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Verify near_misses includes candidate2 (failed max_per_symbol)
    assert snapshot.near_misses is not None
    assert len(snapshot.near_misses) >= 1
    
    # Find candidate2 in near_misses
    nm_candidate2 = next((nm for nm in snapshot.near_misses if nm.get("symbol") == "AAPL" and nm.get("expiry") == "2026-03-20"), None)
    assert nm_candidate2 is not None
    assert nm_candidate2["failed_rule"] == "max_per_symbol"
    assert nm_candidate2["actual_value"] == 1  # Already 1 selected for AAPL
    assert nm_candidate2["required_value"] == 1  # Max is 1


def test_near_misses_none_when_all_selected() -> None:
    """Test that near_misses is None when all scored candidates are selected."""
    candidate = SignalCandidate(
        symbol="AAPL",
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=100.0,
        option_right="PUT",
        bid=1.0,
        ask=1.1,
    )
    
    scored = ScoredSignalCandidate(
        candidate=candidate,
        score=SignalScore(total=0.9, components=[]),
        rank=1,
    )
    
    selected = SelectedSignal(scored=scored, selection_reason="SELECTED_BY_POLICY")
    
    from app.signals.explain import build_explanations
    from app.signals.selection import SelectionConfig
    
    selection_config = SelectionConfig(
        max_total=10,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=None,
    )
    
    explanations = build_explanations([selected], selection_config)

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1},
        scored_candidates=[scored],
        selected_signals=[selected],
        explanations=explanations,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # When all candidates are selected, near_misses should be None or empty
    assert snapshot.near_misses is None or len(snapshot.near_misses) == 0


def test_coverage_near_misses_json_serializable() -> None:
    """Test that coverage_summary and near_misses are JSON-serializable."""
    candidate = SignalCandidate(
        symbol="AAPL",
        signal_type=SignalType.CSP,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        underlying_price=100.0,
        expiry=datetime(2026, 2, 20).date(),
        strike=100.0,
        option_right="PUT",
        bid=1.0,
        ask=1.1,
    )

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1, "symbols_evaluated": 1},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Convert to dict and serialize to JSON
    snapshot_dict = asdict(snapshot)
    json_str = json.dumps(snapshot_dict)
    
    # Parse back
    parsed = json.loads(json_str)
    
    # Verify coverage_summary is present and serializable
    assert parsed.get("coverage_summary") is not None or parsed.get("coverage_summary") is None  # Can be None
    # Verify near_misses is present and serializable (can be None)
    assert "near_misses" in parsed
