from __future__ import annotations

from datetime import datetime, timedelta

from app.execution.execution_gate import ExecutionGateResult, evaluate_execution_gate
from app.signals.decision_snapshot import DecisionSnapshot


def _make_snapshot(
    as_of: str | None = None,
    selected_signals: list[dict] | None = None,
    explanations: list[dict] | None = None,
    symbols_evaluated: int = 1,
) -> DecisionSnapshot:
    """Helper to create a test DecisionSnapshot."""
    if as_of is None:
        as_of = datetime.now().isoformat()

    return DecisionSnapshot(
        as_of=as_of,
        universe_id_or_hash="test",
        stats={"symbols_evaluated": symbols_evaluated, "total_candidates": 1},
        candidates=[],
        scored_candidates=None,
        selected_signals=selected_signals,
        explanations=explanations,
    )


def test_gate_allows_valid_snapshot() -> None:
    """Gate should allow execution for a valid snapshot."""
    selected = [
        {
            "scored": {
                "score": {"total": 0.85},
                "rank": 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
    ]
    explanations = [
        {
            "policy_snapshot": {
                "max_total": 10,
                "max_per_symbol": 5,
                "max_per_signal_type": None,
                "min_score": 0.5,
            }
        }
    ]

    snapshot = _make_snapshot(
        selected_signals=selected,
        explanations=explanations,
        symbols_evaluated=1,
    )

    result = evaluate_execution_gate(snapshot)

    assert result.allowed is True
    assert len(result.reasons) == 0


def test_gate_blocks_no_selected_signals() -> None:
    """Gate should block when selected_signals is None."""
    snapshot = _make_snapshot(selected_signals=None, symbols_evaluated=1)

    result = evaluate_execution_gate(snapshot)

    assert result.allowed is False
    assert "NO_SELECTED_SIGNALS" in result.reasons


def test_gate_blocks_empty_selected_signals() -> None:
    """Gate should block when selected_signals is empty."""
    snapshot = _make_snapshot(selected_signals=[], symbols_evaluated=1)

    result = evaluate_execution_gate(snapshot)

    assert result.allowed is False
    assert "NO_SELECTED_SIGNALS" in result.reasons


def test_gate_blocks_score_below_min() -> None:
    """Gate should block when a signal score is below policy min_score."""
    selected = [
        {
            "scored": {
                "score": {"total": 0.3},  # Below min_score of 0.5
                "rank": 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
    ]
    explanations = [
        {
            "policy_snapshot": {
                "max_total": 10,
                "max_per_symbol": 5,
                "max_per_signal_type": None,
                "min_score": 0.5,
            }
        }
    ]

    snapshot = _make_snapshot(
        selected_signals=selected,
        explanations=explanations,
        symbols_evaluated=1,
    )

    result = evaluate_execution_gate(snapshot)

    assert result.allowed is False
    assert any("SIGNAL_SCORE_BELOW_MIN" in r for r in result.reasons)


def test_gate_blocks_count_exceeds_max() -> None:
    """Gate should block when selected count exceeds policy max_total."""
    # Create 3 selected signals but max_total is 2
    selected = [
        {
            "scored": {
                "score": {"total": 0.85},
                "rank": i + 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
        for i in range(3)
    ]
    explanations = [
        {
            "policy_snapshot": {
                "max_total": 2,  # Less than selected count
                "max_per_symbol": 5,
                "max_per_signal_type": None,
                "min_score": 0.0,
            }
        }
    ]

    snapshot = _make_snapshot(
        selected_signals=selected,
        explanations=explanations,
        symbols_evaluated=1,
    )

    result = evaluate_execution_gate(snapshot)

    assert result.allowed is False
    assert any("SELECTED_COUNT_EXCEEDS_MAX" in r for r in result.reasons)


def test_gate_blocks_no_symbols_evaluated() -> None:
    """Gate should block when no symbols were evaluated."""
    selected = [
        {
            "scored": {
                "score": {"total": 0.85},
                "rank": 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
    ]

    snapshot = _make_snapshot(
        selected_signals=selected,
        explanations=None,
        symbols_evaluated=0,  # No symbols evaluated
    )

    result = evaluate_execution_gate(snapshot)

    assert result.allowed is False
    assert "NO_SYMBOLS_EVALUATED" in result.reasons


def test_gate_blocks_stale_snapshot() -> None:
    """Gate should block when snapshot is older than threshold."""
    # Create a snapshot that's 10 minutes old
    old_time = (datetime.now() - timedelta(minutes=10)).isoformat()

    selected = [
        {
            "scored": {
                "score": {"total": 0.85},
                "rank": 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
    ]

    snapshot = _make_snapshot(
        as_of=old_time,
        selected_signals=selected,
        explanations=None,
        symbols_evaluated=1,
    )

    result = evaluate_execution_gate(snapshot, max_age_minutes=5.0)

    assert result.allowed is False
    assert any("SNAPSHOT_STALE" in r for r in result.reasons)


def test_gate_allows_fresh_snapshot() -> None:
    """Gate should allow when snapshot is within age threshold."""
    # Create a snapshot that's 2 minutes old (within 5 minute threshold)
    fresh_time = (datetime.now() - timedelta(minutes=2)).isoformat()

    selected = [
        {
            "scored": {
                "score": {"total": 0.85},
                "rank": 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
    ]

    snapshot = _make_snapshot(
        as_of=fresh_time,
        selected_signals=selected,
        explanations=None,
        symbols_evaluated=1,
    )

    result = evaluate_execution_gate(snapshot, max_age_minutes=5.0)

    assert result.allowed is True
    assert len(result.reasons) == 0


def test_gate_deterministic() -> None:
    """Gate evaluation should be deterministic."""
    selected = [
        {
            "scored": {
                "score": {"total": 0.85},
                "rank": 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
    ]

    snapshot = _make_snapshot(
        selected_signals=selected,
        explanations=None,
        symbols_evaluated=1,
    )

    result1 = evaluate_execution_gate(snapshot)
    result2 = evaluate_execution_gate(snapshot)

    assert result1.allowed == result2.allowed
    assert result1.reasons == result2.reasons


def test_gate_blocks_invalid_as_of() -> None:
    """Gate should block when as_of cannot be parsed."""
    selected = [
        {
            "scored": {
                "score": {"total": 0.85},
                "rank": 1,
            },
            "selection_reason": "SELECTED_BY_POLICY",
        }
    ]

    snapshot = _make_snapshot(
        as_of="invalid-datetime-string",
        selected_signals=selected,
        explanations=None,
        symbols_evaluated=1,
    )

    result = evaluate_execution_gate(snapshot)

    assert result.allowed is False
    assert "SNAPSHOT_AS_OF_INVALID" in result.reasons
