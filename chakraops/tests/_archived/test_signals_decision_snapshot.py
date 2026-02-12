from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime

from app.signals.decision_snapshot import DecisionSnapshot, build_decision_snapshot
from app.signals.engine import SignalRunResult
from app.signals.explain import SignalExplanation
from app.signals.models import (
    CCConfig,
    CSPConfig,
    ExclusionReason,
    ExclusionDetail,
    SignalCandidate,
    SignalEngineConfig,
    SignalType,
)
from app.signals.scoring import ScoredSignalCandidate, ScoreComponent, SignalScore
from app.signals.selection import SelectedSignal


def _make_candidate(
    symbol: str,
    signal_type: SignalType,
) -> SignalCandidate:
    """Helper to create a test candidate."""
    return SignalCandidate(
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


def test_snapshot_deterministic() -> None:
    """Snapshot build should be deterministic."""
    candidate = _make_candidate("AAPL", SignalType.CSP)

    result1 = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    result2 = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snap1 = build_decision_snapshot(result1)
    snap2 = build_decision_snapshot(result2)

    assert snap1.as_of == snap2.as_of
    assert snap1.universe_id_or_hash == snap2.universe_id_or_hash
    assert snap1.stats == snap2.stats
    assert len(snap1.candidates) == len(snap2.candidates)


def test_snapshot_mirrors_result() -> None:
    """Snapshot should mirror SignalRunResult content."""
    candidate = _make_candidate("AAPL", SignalType.CSP)

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test_universe",
        configs={"base": {"dte_min": 25}},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1, "csp_candidates": 1},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    assert snapshot.universe_id_or_hash == result.universe_id_or_hash
    assert snapshot.stats == result.stats
    assert len(snapshot.candidates) == len(result.candidates)
    assert snapshot.candidates[0]["symbol"] == candidate.symbol
    assert snapshot.candidates[0]["signal_type"] == candidate.signal_type.value


def test_json_round_trip() -> None:
    """Snapshot should be JSON-serializable and round-trip correctly."""
    candidate = _make_candidate("AAPL", SignalType.CSP)

    # Create scored candidate
    scored = ScoredSignalCandidate(
        candidate=candidate,
        score=SignalScore(
            total=0.85,
            components=[
                ScoreComponent(name="premium_score", value=0.5, weight=1.0)
            ],
        ),
        rank=1,
    )

    # Create selected signal
    selected = SelectedSignal(scored=scored, selection_reason="SELECTED_BY_POLICY")

    # Create explanation
    explanation = SignalExplanation(
        symbol="AAPL",
        signal_type="CSP",
        rank=1,
        total_score=0.85,
        score_components=[ScoreComponent(name="premium_score", value=0.5, weight=1.0)],
        selection_reason="SELECTED_BY_POLICY",
        policy_snapshot={"max_total": 1, "max_per_symbol": 1},
    )

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1},
        scored_candidates=[scored],
        selected_signals=[selected],
        explanations=[explanation],
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Convert to dict and serialize to JSON
    snapshot_dict = asdict(snapshot)
    json_str = json.dumps(snapshot_dict)

    # Parse back
    parsed = json.loads(json_str)

    # Verify structure
    assert parsed["universe_id_or_hash"] == "test"
    assert parsed["stats"]["total_candidates"] == 1
    assert len(parsed["candidates"]) == 1
    assert parsed["candidates"][0]["symbol"] == "AAPL"
    assert parsed["scored_candidates"] is not None
    assert parsed["selected_signals"] is not None
    assert parsed["explanations"] is not None


def test_snapshot_without_scoring_selection() -> None:
    """Snapshot should work when scoring/selection are disabled."""
    candidate = _make_candidate("AAPL", SignalType.CSP)

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],
        stats={"total_candidates": 1},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    assert snapshot.scored_candidates is None
    assert snapshot.selected_signals is None
    assert snapshot.explanations is None
    assert len(snapshot.candidates) == 1
    assert snapshot.stats["total_candidates"] == 1

    # Should still be JSON-serializable
    snapshot_dict = asdict(snapshot)
    json_str = json.dumps(snapshot_dict)
    parsed = json.loads(json_str)
    assert parsed["scored_candidates"] is None
    assert parsed["selected_signals"] is None
    assert parsed["explanations"] is None


def test_decision_snapshot_with_exclusions() -> None:
    """Snapshot should include exclusion details when present (Phase 7.2)."""
    candidate = _make_candidate("AAPL", SignalType.CSP)
    
    exclusions = [
        ExclusionReason(
            code="NO_OPTIONS_FOR_SYMBOL",
            message="AAPL: No PUT options found for AAPL",
            data={"symbol": "AAPL", "total_options": 0},
        ),
        ExclusionReason(
            code="NO_EXPIRY_IN_DTE_WINDOW",
            message="MSFT: No expirations in DTE window [30, 45]",
            data={"symbol": "MSFT", "dte_min": 30, "dte_max": 45},
        ),
    ]

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=exclusions,
        stats={"total_candidates": 1, "total_exclusions": 2},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Verify exclusions are present
    assert snapshot.exclusions is not None
    assert len(snapshot.exclusions) == 2
    
    # Verify exclusion structure
    excl1 = snapshot.exclusions[0]
    assert excl1["symbol"] == "AAPL"
    assert excl1["rule"] == "NO_OPTIONS_FOR_SYMBOL"
    assert excl1["message"] == "AAPL: No PUT options found for AAPL"
    assert excl1["stage"] in ("CSP_GENERATION", "NORMALIZATION", "UNKNOWN")
    
    excl2 = snapshot.exclusions[1]
    assert excl2["symbol"] == "MSFT"
    assert excl2["rule"] == "NO_EXPIRY_IN_DTE_WINDOW"
    
    # Verify JSON serialization
    snapshot_dict = asdict(snapshot)
    json_str = json.dumps(snapshot_dict)
    parsed = json.loads(json_str)
    assert parsed["exclusions"] is not None
    assert len(parsed["exclusions"]) == 2


def test_decision_snapshot_without_exclusions() -> None:
    """Snapshot should have exclusions=None when no exclusions present (backward compatibility)."""
    candidate = _make_candidate("AAPL", SignalType.CSP)

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=[],  # Empty list
        stats={"total_candidates": 1},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Empty exclusions list should result in None (backward compatibility)
    assert snapshot.exclusions is None
