"""Tests for exclusion summary diagnostics (Phase 7.3)."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from app.signals.decision_snapshot import (
    DecisionSnapshot,
    _build_exclusion_summary,
    _derive_operator_verdict,
    build_decision_snapshot,
)
from app.signals.engine import SignalRunResult
from app.signals.models import ExclusionReason, SignalCandidate, SignalType


def test_exclusion_summary_present() -> None:
    """Test that exclusion_summary is built when exclusions exist."""
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

    exclusions = [
        ExclusionReason(
            code="NO_OPTIONS_FOR_SYMBOL",
            message="AAPL: No PUT options found",
            data={"symbol": "AAPL"},
        ),
        ExclusionReason(
            code="NO_OPTIONS_FOR_SYMBOL",
            message="MSFT: No PUT options found",
            data={"symbol": "MSFT"},
        ),
        ExclusionReason(
            code="NO_EXPIRY_IN_DTE_WINDOW",
            message="GOOGL: No expirations in DTE window",
            data={"symbol": "GOOGL"},
        ),
    ]

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=exclusions,
        stats={"total_candidates": 1, "total_exclusions": 3},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Verify exclusion_summary is present
    assert snapshot.exclusion_summary is not None
    
    summary = snapshot.exclusion_summary
    assert "rule_counts" in summary
    assert "stage_counts" in summary
    assert "symbols_by_rule" in summary
    
    # Verify rule counts
    rule_counts = summary["rule_counts"]
    assert rule_counts["NO_OPTIONS_FOR_SYMBOL"] == 2
    assert rule_counts["NO_EXPIRY_IN_DTE_WINDOW"] == 1
    
    # Verify symbols by rule
    symbols_by_rule = summary["symbols_by_rule"]
    assert "AAPL" in symbols_by_rule.get("NO_OPTIONS_FOR_SYMBOL", [])
    assert "MSFT" in symbols_by_rule.get("NO_OPTIONS_FOR_SYMBOL", [])
    assert "GOOGL" in symbols_by_rule.get("NO_EXPIRY_IN_DTE_WINDOW", [])


def test_exclusion_summary_absent() -> None:
    """Test that exclusion_summary is None when exclusions are empty (backward compatibility)."""
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
        exclusions=[],  # Empty list
        stats={"total_candidates": 1},
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        decision_snapshot=None,
    )

    snapshot = build_decision_snapshot(result)

    # Verify exclusion_summary is None when exclusions are empty
    assert snapshot.exclusion_summary is None


def test_build_exclusion_summary_empty() -> None:
    """Test _build_exclusion_summary returns None for empty input."""
    summary = _build_exclusion_summary([])
    assert summary is None


def test_build_exclusion_summary_with_data() -> None:
    """Test _build_exclusion_summary aggregates correctly."""
    exclusion_details = [
        {"rule": "RULE_A", "stage": "STAGE_1", "symbol": "AAPL"},
        {"rule": "RULE_A", "stage": "STAGE_1", "symbol": "MSFT"},
        {"rule": "RULE_B", "stage": "STAGE_2", "symbol": "GOOGL"},
    ]
    
    summary = _build_exclusion_summary(exclusion_details)
    
    assert summary is not None
    assert summary["rule_counts"]["RULE_A"] == 2
    assert summary["rule_counts"]["RULE_B"] == 1
    assert summary["stage_counts"]["STAGE_1"] == 2
    assert summary["stage_counts"]["STAGE_2"] == 1
    assert "AAPL" in summary["symbols_by_rule"]["RULE_A"]
    assert "MSFT" in summary["symbols_by_rule"]["RULE_A"]
    assert "GOOGL" in summary["symbols_by_rule"]["RULE_B"]


def test_derive_operator_verdict() -> None:
    """Test _derive_operator_verdict generates correct verdict."""
    exclusion_summary = {
        "rule_counts": {
            "NO_OPTIONS_FOR_SYMBOL": 3,
            "NO_EXPIRY_IN_DTE_WINDOW": 1,
        },
        "stage_counts": {
            "NORMALIZATION": 3,
            "CSP_GENERATION": 1,
        },
        "symbols_by_rule": {
            "NO_OPTIONS_FOR_SYMBOL": ["AAPL", "MSFT", "GOOGL"],
            "NO_EXPIRY_IN_DTE_WINDOW": ["TSLA"],
        },
    }
    
    verdict = _derive_operator_verdict(exclusion_summary)
    
    assert "NO_OPTIONS_FOR_SYMBOL" in verdict
    assert "3" in verdict  # Count
    assert "AAPL" in verdict or "MSFT" in verdict or "GOOGL" in verdict


def test_derive_operator_verdict_none() -> None:
    """Test _derive_operator_verdict handles None input."""
    verdict = _derive_operator_verdict(None)
    assert "No exclusion data" in verdict


def test_derive_operator_verdict_empty() -> None:
    """Test _derive_operator_verdict handles empty summary."""
    verdict = _derive_operator_verdict({"rule_counts": {}})
    assert "No exclusion rules" in verdict


def test_exclusion_summary_json_serializable() -> None:
    """Test that exclusion_summary is JSON-serializable."""
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

    exclusions = [
        ExclusionReason(
            code="NO_OPTIONS_FOR_SYMBOL",
            message="AAPL: No PUT options found",
            data={"symbol": "AAPL"},
        ),
    ]

    result = SignalRunResult(
        as_of=datetime(2026, 1, 22, 10, 0, 0),
        universe_id_or_hash="test",
        configs={},
        candidates=[candidate],
        exclusions=exclusions,
        stats={"total_candidates": 1},
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
    
    # Verify exclusion_summary is present and serializable
    assert parsed["exclusion_summary"] is not None
    assert "rule_counts" in parsed["exclusion_summary"]
