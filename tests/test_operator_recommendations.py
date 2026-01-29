"""Tests for Operator Action Recommendations (Phase 8.1)."""

import json
from unittest.mock import patch

import pytest

from app.ui.operator_recommendations import (
    OperatorRecommendation,
    RecommendationSeverity,
    generate_operator_recommendations,
)
from app.ui.sandbox import SandboxResult


def test_operator_recommendation():
    """Test OperatorRecommendation dataclass."""
    rec = OperatorRecommendation(
        severity=RecommendationSeverity.HIGH,
        title="Test Recommendation",
        action="Do something",
        evidence=["Evidence 1", "Evidence 2"],
        category="TEST",
    )
    assert rec.severity == RecommendationSeverity.HIGH
    assert rec.title == "Test Recommendation"
    assert rec.action == "Do something"
    assert len(rec.evidence) == 2
    assert rec.category == "TEST"


def test_generate_recommendations_empty_snapshot():
    """Test recommendations with empty snapshot."""
    snapshot = {}
    
    recommendations = generate_operator_recommendations(snapshot)
    
    assert isinstance(recommendations, list)
    # May have some recommendations or none, depending on data


def test_recommendation_data_availability():
    """Test data availability recommendation."""
    snapshot = {
        "exclusion_summary": {
            "rule_counts": {
                "CHAIN_FETCH_ERROR": 3,
                "NO_EXPIRATIONS": 2,
            },
            "stage_counts": {},
            "symbols_by_rule": {},
        },
        "coverage_summary": {
            "by_symbol": {
                "AAPL": {"generation": 0, "scoring": 0, "selection": 0},
                "MSFT": {"generation": 0, "scoring": 0, "selection": 0},
            },
        },
    }
    
    recommendations = generate_operator_recommendations(snapshot)
    
    # Should have data availability recommendation
    data_recs = [r for r in recommendations if r.category == "DATA_AVAILABILITY"]
    assert len(data_recs) > 0
    
    data_rec = data_recs[0]
    assert data_rec.severity == RecommendationSeverity.HIGH
    assert "data provider" in data_rec.action.lower() or "connectivity" in data_rec.action.lower()


def test_recommendation_near_miss_min_score():
    """Test near-miss recommendation for min_score."""
    snapshot = {
        "near_misses": [
            {
                "symbol": "AAPL",
                "strategy": "CSP",
                "failed_rule": "min_score",
                "actual_value": 0.45,
                "required_value": 0.50,
                "stage": "SELECTION",
            },
            {
                "symbol": "MSFT",
                "strategy": "CC",
                "failed_rule": "min_score",
                "actual_value": 0.48,
                "required_value": 0.50,
                "stage": "SELECTION",
            },
        ],
    }
    
    recommendations = generate_operator_recommendations(snapshot)
    
    # Should have min_score recommendation
    score_recs = [
        r for r in recommendations
        if r.category == "CONFIG_TUNING" and "min_score" in r.title.lower()
    ]
    assert len(score_recs) > 0
    
    score_rec = score_recs[0]
    assert score_rec.severity == RecommendationSeverity.MEDIUM
    assert "min_score" in score_rec.action.lower()


def test_recommendation_near_miss_max_per_symbol():
    """Test near-miss recommendation for max_per_symbol."""
    snapshot = {
        "near_misses": [
            {
                "symbol": "AAPL",
                "strategy": "CSP",
                "failed_rule": "max_per_symbol",
                "actual_value": 2,
                "required_value": 2,
                "stage": "SELECTION",
            },
            {
                "symbol": "AAPL",
                "strategy": "CC",
                "failed_rule": "max_per_symbol",
                "actual_value": 2,
                "required_value": 2,
                "stage": "SELECTION",
            },
        ],
    }
    
    recommendations = generate_operator_recommendations(snapshot)
    
    # Should have max_per_symbol recommendation
    cap_recs = [
        r for r in recommendations
        if r.category == "CONFIG_TUNING" and "max_per_symbol" in r.title.lower()
    ]
    assert len(cap_recs) > 0
    
    cap_rec = cap_recs[0]
    assert cap_rec.severity == RecommendationSeverity.LOW
    assert "max_per_symbol" in cap_rec.action.lower()


def test_recommendation_coverage_high_attrition():
    """Test coverage recommendation for high attrition."""
    snapshot = {
        "coverage_summary": {
            "by_symbol": {
                "AAPL": {
                    "generation": 10,
                    "scoring": 8,
                    "selection": 0,
                },
                "MSFT": {
                    "generation": 15,
                    "scoring": 12,
                    "selection": 0,
                },
                "GOOGL": {
                    "generation": 2,
                    "scoring": 2,
                    "selection": 1,
                },
            },
        },
    }
    
    recommendations = generate_operator_recommendations(snapshot)
    
    # Should have coverage recommendation
    coverage_recs = [r for r in recommendations if r.category == "COVERAGE"]
    assert len(coverage_recs) > 0
    
    coverage_rec = coverage_recs[0]
    assert coverage_rec.severity == RecommendationSeverity.MEDIUM
    assert "attrition" in coverage_rec.title.lower() or "scoring" in coverage_rec.action.lower()


def test_recommendation_sandbox_insights():
    """Test sandbox-based recommendation."""
    snapshot = {
        "scored_candidates": [],
        "selected_signals": [],
    }
    
    sandbox_result = SandboxResult(
        selected_count=5,
        selected_signals=[],
        newly_admitted=[
            {
                "scored": {
                    "candidate": {"symbol": "AAPL", "signal_type": "CSP"},
                    "score": {"total": 0.45},
                }
            }
        ],
        rejected_reasons={
            "('AAPL', 'CSP', '2026-02-20', 150.0)": "min_score: 0.4500 < 0.5000",
        },
    )
    
    recommendations = generate_operator_recommendations(snapshot, sandbox_result=sandbox_result)
    
    # Should have sandbox recommendation
    sandbox_recs = [
        r for r in recommendations
        if r.category == "CONFIG_TUNING" and "sandbox" in r.title.lower()
    ]
    assert len(sandbox_recs) > 0
    
    sandbox_rec = sandbox_recs[0]
    assert sandbox_rec.severity == RecommendationSeverity.MEDIUM


def test_recommendation_severity_ordering():
    """Test that recommendations are sorted by severity."""
    snapshot = {
        "exclusion_summary": {
            "rule_counts": {"CHAIN_FETCH_ERROR": 1},
            "stage_counts": {},
            "symbols_by_rule": {},
        },
        "near_misses": [
            {
                "symbol": "AAPL",
                "failed_rule": "max_per_symbol",
                "actual_value": 2,
                "required_value": 2,
            }
        ],
    }
    
    recommendations = generate_operator_recommendations(snapshot)
    
    # Should be sorted HIGH -> MEDIUM -> LOW
    if len(recommendations) > 1:
        severity_order = {
            RecommendationSeverity.HIGH: 0,
            RecommendationSeverity.MEDIUM: 1,
            RecommendationSeverity.LOW: 2,
        }
        
        for i in range(len(recommendations) - 1):
            current_sev = severity_order.get(recommendations[i].severity, 99)
            next_sev = severity_order.get(recommendations[i + 1].severity, 99)
            assert current_sev <= next_sev


def test_recommendation_no_mutation():
    """Test that recommendation generation does not mutate snapshot."""
    snapshot = {
        "exclusion_summary": {
            "rule_counts": {"CHAIN_FETCH_ERROR": 1},
            "stage_counts": {},
            "symbols_by_rule": {},
        },
    }
    snapshot_copy = json.loads(json.dumps(snapshot))  # Deep copy
    
    generate_operator_recommendations(snapshot)
    
    # Snapshot should be unchanged
    assert snapshot == snapshot_copy


def test_recommendation_empty_no_op():
    """Test that empty/normal snapshot produces no recommendations or low-severity ones."""
    snapshot = {
        "selected_signals": [
            {
                "scored": {
                    "candidate": {"symbol": "AAPL"},
                }
            }
        ],
        "coverage_summary": {
            "by_symbol": {
                "AAPL": {"generation": 5, "scoring": 5, "selection": 2},
            },
        },
    }
    
    recommendations = generate_operator_recommendations(snapshot)
    
    # Should have no HIGH severity recommendations for normal operation
    high_recs = [r for r in recommendations if r.severity == RecommendationSeverity.HIGH]
    assert len(high_recs) == 0


__all__ = [
    "test_operator_recommendation",
    "test_generate_recommendations_empty_snapshot",
    "test_recommendation_data_availability",
    "test_recommendation_near_miss_min_score",
    "test_recommendation_near_miss_max_per_symbol",
    "test_recommendation_coverage_high_attrition",
    "test_recommendation_sandbox_insights",
    "test_recommendation_severity_ordering",
    "test_recommendation_no_mutation",
    "test_recommendation_empty_no_op",
]
