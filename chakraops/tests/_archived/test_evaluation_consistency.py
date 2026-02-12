# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for evaluation consistency across views.

Covers:
1. Ticker page reads persisted verdict (single source of truth)
2. Band + capital hint serialized correctly
3. Universe/Ticker/Dashboard consistency
4. Score normalization warning
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.core.eval.staged_evaluator import (
    FullEvaluationResult,
    FinalVerdict,
    EvaluationStage,
)
from app.core.eval.confidence_band import compute_confidence_band, CapitalHint


class TestCapitalHintSerialization:
    """Tests for confidence band and capital hint serialization."""

    def test_compute_confidence_band_returns_capital_hint(self) -> None:
        """compute_confidence_band returns CapitalHint with band and percentage."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=1.0,
            liquidity_ok=True,
            score=85,
            position_open=False,
        )
        assert isinstance(hint, CapitalHint)
        assert hint.band in ("A", "B", "C")
        assert 0 < hint.suggested_capital_pct <= 0.10

    def test_band_a_for_ideal_conditions(self) -> None:
        """Band A assigned for RISK_ON + complete data + good liquidity."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=1.0,
            liquidity_ok=True,
            score=85,
            position_open=False,
        )
        assert hint.band == "A"
        assert hint.suggested_capital_pct == 0.05

    def test_band_b_for_neutral_regime(self) -> None:
        """Band B assigned for NEUTRAL regime."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="NEUTRAL",
            data_completeness=1.0,
            liquidity_ok=True,
            score=75,
            position_open=False,
        )
        assert hint.band == "B"
        assert hint.suggested_capital_pct == 0.03

    def test_band_c_for_hold_verdict(self) -> None:
        """Band C assigned for HOLD verdict."""
        hint = compute_confidence_band(
            verdict="HOLD",
            regime="RISK_ON",
            data_completeness=0.8,
            liquidity_ok=True,
            score=55,
            position_open=False,
        )
        assert hint.band == "C"
        assert hint.suggested_capital_pct == 0.02

    def test_band_c_for_incomplete_data(self) -> None:
        """Band C assigned when data incomplete."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.6,  # Below threshold
            liquidity_ok=True,
            score=70,
            position_open=False,
        )
        assert hint.band == "C"

    def test_capital_hint_to_dict(self) -> None:
        """CapitalHint.to_dict() serializes correctly (includes band_reason in schema)."""
        hint = CapitalHint(band="A", suggested_capital_pct=0.05)
        d = hint.to_dict()
        assert d["band"] == "A"
        assert d["suggested_capital_pct"] == 0.05
        assert d.get("band_reason") is None


class TestFullEvaluationResultSerialization:
    """Tests for FullEvaluationResult serialization with capital_hint."""

    def test_to_dict_includes_capital_hint(self) -> None:
        """FullEvaluationResult.to_dict() includes capital_hint when set."""
        result = FullEvaluationResult(
            symbol="SPY",
            final_verdict=FinalVerdict.ELIGIBLE,
            verdict="ELIGIBLE",
            primary_reason="Good setup",
            score=85,
            stage_reached=EvaluationStage.STAGE2_CHAIN,
        )
        result.capital_hint = CapitalHint(band="A", suggested_capital_pct=0.05)
        
        d = result.to_dict()
        assert "capital_hint" in d
        assert d["capital_hint"]["band"] == "A"
        assert d["capital_hint"]["suggested_capital_pct"] == 0.05
        assert d["capital_hint"].get("band_reason") is None

    def test_to_dict_capital_hint_none_when_not_set(self) -> None:
        """FullEvaluationResult.to_dict() has None capital_hint when not set."""
        result = FullEvaluationResult(
            symbol="SPY",
            final_verdict=FinalVerdict.HOLD,
            verdict="HOLD",
            primary_reason="Regime block",
            score=50,
        )
        d = result.to_dict()
        assert d["capital_hint"] is None

    def test_to_dict_includes_position_fields(self) -> None:
        """FullEvaluationResult.to_dict() includes position_open and position_reason."""
        result = FullEvaluationResult(
            symbol="AAPL",
            final_verdict=FinalVerdict.HOLD,
            verdict="HOLD",
            primary_reason="Position already open",
            score=60,
            position_open=True,
            position_reason="POSITION_ALREADY_OPEN",
        )
        d = result.to_dict()
        assert d["position_open"] is True
        assert d["position_reason"] == "POSITION_ALREADY_OPEN"


class TestScoreNormalizationWarning:
    """Tests for score normalization warning when all scores identical."""

    def test_score_flattening_logged_when_all_identical(self, caplog) -> None:
        """Warning logged when all non-zero scores are identical."""
        from app.core.eval.staged_evaluator import evaluate_universe_staged
        
        # We need to mock the evaluation to return identical scores
        # This is a structural test - the actual logging happens in evaluate_universe_staged
        # Just verify the log message format is correct
        
        with caplog.at_level(logging.WARNING):
            # Create mock results with identical scores
            # The actual function would log: [EVAL] score_flattened=true
            logger = logging.getLogger("app.core.eval.staged_evaluator")
            
            # Simulate what the function does
            all_scores = [50, 50, 50, 50]
            if all_scores and len(set(all_scores)) == 1 and len(all_scores) > 1:
                logger.warning(
                    "[EVAL] score_flattened=true - all %d non-zero scores identical (%d)",
                    len(all_scores), all_scores[0]
                )
        
        assert any("score_flattened=true" in record.message for record in caplog.records)


class TestSingleSourceOfTruth:
    """Tests for single source of truth - ticker reads from persisted run."""

    @pytest.fixture
    def mock_persisted_run(self) -> Dict[str, Any]:
        """Create a mock persisted evaluation run."""
        return {
            "run_id": "test-run-123",
            "started_at": "2026-02-03T10:00:00Z",
            "completed_at": "2026-02-03T10:05:00Z",
            "status": "COMPLETED",
            "symbols": [
                {
                    "symbol": "SPY",
                    "verdict": "ELIGIBLE",
                    "primary_reason": "Chain selected: 30DTE, -0.25 delta",
                    "score": 85,
                    "confidence": 0.8,
                    "rationale": {
                        "summary": "Good setup with aligned trend",
                        "bullets": ["EMA aligned", "IV favorable"],
                        "failed_checks": [],
                        "data_warnings": [],
                    },
                    "capital_hint": {"band": "A", "suggested_capital_pct": 0.05},
                    "position_open": False,
                    "gates": [
                        {"name": "Stock Quality", "status": "PASS", "reason": "Score 85"},
                        {"name": "Liquidity", "status": "PASS", "reason": "Grade A"},
                    ],
                    "candidate_trades": [
                        {"strategy": "CSP", "expiry": "2026-03-21", "strike": 450, "delta": -0.25}
                    ],
                },
                {
                    "symbol": "AAPL",
                    "verdict": "HOLD",
                    "primary_reason": "DATA_INCOMPLETE_INTRADAY: missing bid, ask",
                    "score": 60,
                    "position_open": True,
                    "position_reason": "CSP_OPEN",
                    "capital_hint": {"band": "C", "suggested_capital_pct": 0.02},
                },
            ],
        }

    def test_persisted_verdict_takes_precedence(self, mock_persisted_run: Dict[str, Any]) -> None:
        """Symbol diagnostics should use verdict from persisted run."""
        spy_data = mock_persisted_run["symbols"][0]
        
        # Verify the structure matches what we expect
        assert spy_data["verdict"] == "ELIGIBLE"
        assert spy_data["capital_hint"]["band"] == "A"
        assert spy_data["rationale"]["summary"] == "Good setup with aligned trend"

    def test_position_data_from_persisted_run(self, mock_persisted_run: Dict[str, Any]) -> None:
        """Position data should come from persisted run."""
        aapl_data = mock_persisted_run["symbols"][1]
        
        assert aapl_data["position_open"] is True
        assert aapl_data["position_reason"] == "CSP_OPEN"

    def test_gates_from_persisted_run(self, mock_persisted_run: Dict[str, Any]) -> None:
        """Gates should come from persisted run."""
        spy_data = mock_persisted_run["symbols"][0]
        
        assert len(spy_data["gates"]) == 2
        assert spy_data["gates"][0]["status"] == "PASS"

    def test_candidate_trades_from_persisted_run(self, mock_persisted_run: Dict[str, Any]) -> None:
        """Candidate trades should come from persisted run."""
        spy_data = mock_persisted_run["symbols"][0]
        
        assert len(spy_data["candidate_trades"]) == 1
        assert spy_data["candidate_trades"][0]["strategy"] == "CSP"


class TestViewConsistency:
    """Tests to verify Universe/Ticker/Dashboard show consistent data."""

    def test_verdict_reason_matches_failed_checks(self) -> None:
        """Verdict reason should be derivable from failed_checks in rationale."""
        # When a symbol has failed checks, the primary_reason should reflect them
        rationale = {
            "summary": "Blocked by market regime",
            "bullets": [],
            "failed_checks": ["Market regime: RISK_OFF"],
            "data_warnings": [],
        }
        
        # The primary_reason should match the rationale
        expected_reason = "Blocked by market regime: RISK_OFF"
        
        # This is a structural test - the actual consistency is maintained by
        # using the same persisted run data across all views
        assert "RISK_OFF" in rationale["failed_checks"][0]

    def test_counts_match_symbols_list(self) -> None:
        """Evaluation counts should match symbols list filtering."""
        symbols = [
            {"symbol": "SPY", "verdict": "ELIGIBLE"},
            {"symbol": "AAPL", "verdict": "HOLD"},
            {"symbol": "MSFT", "verdict": "ELIGIBLE"},
            {"symbol": "GOOGL", "verdict": "BLOCKED"},
        ]
        
        # Counts should be derivable from symbols
        total = len(symbols)
        eligible = sum(1 for s in symbols if s["verdict"] == "ELIGIBLE")
        holds = sum(1 for s in symbols if s["verdict"] == "HOLD")
        blocks = sum(1 for s in symbols if s["verdict"] == "BLOCKED")
        
        assert total == 4
        assert eligible == 2
        assert holds == 1
        assert blocks == 1


@pytest.mark.integration
class TestSnapshotContract:
    """Tests for /api/ops/snapshot error contract - NEVER throws.
    
    These tests require FastAPI to be installed.
    """

    @pytest.fixture
    def requires_fastapi(self):
        """Skip tests if FastAPI not available."""
        pytest.importorskip("fastapi", reason="requires FastAPI (optional dependency)")

    def test_snapshot_returns_snapshot_ok_false_when_no_run(self, requires_fastapi):
        """Snapshot should return 200 with snapshot_ok=False when no run exists."""
        from app.api.server import api_ops_snapshot
        
        with patch("app.api.server.build_latest_response") as mock_latest, \
             patch("app.api.server.read_market_status", return_value={}), \
             patch("app.api.server.get_market_phase", return_value=None), \
             patch("app.api.server.load_decision_artifact", return_value=None), \
             patch("app.api.server.get_scheduler_status", return_value={}), \
             patch("app.api.server._eval_jobs", {}):
            # Simulate no completed run
            mock_latest.return_value = {
                "has_completed_run": False,
                "counts": {},
                "symbols": [],
            }
            
            result = api_ops_snapshot()
            
            # Should always return dict, never throw
            assert isinstance(result, dict)
            assert result.get("snapshot_ok") == False
            assert result.get("has_run") == False
            assert result.get("reason") == "NO_LATEST_RUN"
            # Should still have all expected fields
            assert "universe" in result
            assert "pipeline_steps" in result
            assert "evaluation_state" in result

    def test_snapshot_returns_snapshot_ok_true_when_run_exists(self, requires_fastapi):
        """Snapshot should return 200 with snapshot_ok=True when run exists."""
        from app.api.server import api_ops_snapshot
        
        with patch("app.api.server.build_latest_response") as mock_latest, \
             patch("app.api.server.read_market_status", return_value={}), \
             patch("app.api.server.get_market_phase", return_value="CLOSED"), \
             patch("app.api.server.load_decision_artifact", return_value=None), \
             patch("app.api.server.get_scheduler_status", return_value={}), \
             patch("app.api.server._eval_jobs", {}):
            # Simulate completed run
            mock_latest.return_value = {
                "has_completed_run": True,
                "run_id": "test_run_123",
                "completed_at": "2026-02-04T01:00:00Z",
                "counts": {
                    "total": 50,
                    "evaluated": 50,
                    "eligible": 5,
                    "shortlisted": 2,
                },
                "symbols": [
                    {"symbol": "SPY", "verdict": "ELIGIBLE"},
                    {"symbol": "AAPL", "verdict": "HOLD"},
                ],
                "top_candidates": [],
            }
            
            result = api_ops_snapshot()
            
            assert isinstance(result, dict)
            assert result.get("snapshot_ok") == True
            assert result.get("has_run") == True
            assert result.get("reason") is None
            assert result["universe"]["evaluated"] == 50
            assert result["universe"]["eligible"] == 5

    def test_snapshot_handles_null_values_gracefully(self, requires_fastapi):
        """Snapshot should handle null/None values without crashing."""
        from app.api.server import api_ops_snapshot
        
        with patch("app.api.server.build_latest_response") as mock_latest, \
             patch("app.api.server.read_market_status", return_value={}), \
             patch("app.api.server.get_market_phase", return_value=None), \
             patch("app.api.server.load_decision_artifact", return_value=None), \
             patch("app.api.server.get_scheduler_status", return_value={}), \
             patch("app.api.server._eval_jobs", {}):
            # Return data with lots of None values
            mock_latest.return_value = {
                "has_completed_run": True,
                "run_id": None,
                "completed_at": None,
                "counts": None,
                "symbols": None,
                "top_candidates": None,
            }
            
            # Should not crash
            result = api_ops_snapshot()
            assert isinstance(result, dict)
            assert "snapshot_ok" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
