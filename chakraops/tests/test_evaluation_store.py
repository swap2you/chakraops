# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for evaluation run persistence store."""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.core.eval.evaluation_store import (
    CorruptedRunError,
    EvaluationRunSummary,
    EvaluationRunFull,
    LatestPointer,
    generate_run_id,
    save_run,
    update_latest_pointer,
    load_run,
    load_latest_pointer,
    load_latest_run,
    list_runs,
    delete_old_runs,
    create_run_from_evaluation,
    build_latest_response,
    build_runs_list_response,
    build_run_detail_response,
)


@pytest.fixture
def temp_evaluations_dir(tmp_path):
    """Create a temporary evaluations directory."""
    eval_dir = tmp_path / "evaluations"
    eval_dir.mkdir()
    with patch("app.core.eval.evaluation_store._get_evaluations_dir", return_value=eval_dir):
        yield eval_dir


class TestGenerateRunId:
    """Tests for run ID generation."""

    def test_run_id_format(self):
        """Run ID should have expected format: eval_{timestamp}_{uuid}."""
        run_id = generate_run_id()
        assert run_id.startswith("eval_")
        parts = run_id.split("_")
        assert len(parts) == 4  # eval, date, time, uuid
        assert len(parts[3]) == 8  # short uuid

    def test_run_ids_are_unique(self):
        """Generated run IDs should be unique."""
        ids = [generate_run_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestSaveAndLoadRun:
    """Tests for saving and loading evaluation runs."""

    def test_save_and_load_run(self, temp_evaluations_dir):
        """Save a run and load it back."""
        run = EvaluationRunFull(
            run_id="eval_20260203_120000_abc12345",
            started_at="2026-02-03T12:00:00Z",
            completed_at="2026-02-03T12:01:30Z",
            status="COMPLETED",
            duration_seconds=90.5,
            total=50,
            evaluated=48,
            eligible=12,
            shortlisted=5,
            regime="BULL",
            risk_posture="LOW",
            market_phase="OPEN",
            symbols=[{"symbol": "AAPL", "verdict": "ELIGIBLE", "score": 85}],
            top_candidates=[{"symbol": "AAPL", "verdict": "ELIGIBLE", "score": 85}],
            alerts=[{"id": "a1", "type": "ELIGIBLE", "symbol": "AAPL", "message": "test"}],
            alerts_count=1,
            errors=[],
        )

        save_run(run)

        loaded = load_run("eval_20260203_120000_abc12345")
        assert loaded is not None
        assert loaded.run_id == run.run_id
        assert loaded.status == "COMPLETED"
        assert loaded.total == 50
        assert loaded.evaluated == 48
        assert loaded.eligible == 12
        assert loaded.duration_seconds == 90.5
        assert len(loaded.symbols) == 1
        assert loaded.symbols[0]["symbol"] == "AAPL"

    def test_load_nonexistent_run(self, temp_evaluations_dir):
        """Loading a nonexistent run returns None."""
        result = load_run("nonexistent_run_id")
        assert result is None

    def test_load_run_raises_corrupted_on_checksum_mismatch(self, temp_evaluations_dir):
        """Phase A: When run file is tampered (checksum mismatch), load_run raises CorruptedRunError."""
        run = EvaluationRunFull(
            run_id="eval_corrupt_test",
            started_at="2026-02-03T12:00:00Z",
            status="COMPLETED",
            symbols=[],
        )
        save_run(run)
        path = temp_evaluations_dir / "eval_corrupt_test.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["run_id"] = "tampered"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        with pytest.raises(CorruptedRunError):
            load_run("eval_corrupt_test")


class TestLatestPointer:
    """Tests for latest pointer management."""

    def test_update_and_load_latest_pointer(self, temp_evaluations_dir):
        """Update latest pointer and load it back."""
        update_latest_pointer("eval_test_123", "2026-02-03T12:00:00Z")

        pointer = load_latest_pointer()
        assert pointer is not None
        assert pointer.run_id == "eval_test_123"
        assert pointer.completed_at == "2026-02-03T12:00:00Z"
        assert pointer.status == "COMPLETED"

    def test_load_latest_pointer_missing(self, temp_evaluations_dir):
        """Loading latest pointer when file doesn't exist returns None."""
        result = load_latest_pointer()
        assert result is None

    def test_load_latest_run(self, temp_evaluations_dir):
        """Load latest run combines pointer and run data."""
        # Save a run
        run = EvaluationRunFull(
            run_id="eval_latest_test",
            started_at="2026-02-03T12:00:00Z",
            completed_at="2026-02-03T12:01:00Z",
            status="COMPLETED",
            total=10,
            evaluated=10,
            eligible=3,
            shortlisted=1,
        )
        save_run(run)
        update_latest_pointer(run.run_id, run.completed_at)

        loaded = load_latest_run()
        assert loaded is not None
        assert loaded.run_id == "eval_latest_test"
        assert loaded.eligible == 3


class TestListRuns:
    """Tests for listing evaluation runs."""

    def test_list_runs_empty(self, temp_evaluations_dir):
        """Listing runs when none exist returns empty list."""
        result = list_runs()
        assert result == []

    def test_list_runs_returns_summaries(self, temp_evaluations_dir):
        """List runs returns summaries sorted by newest first."""
        # Create multiple runs
        for i in range(3):
            run = EvaluationRunFull(
                run_id=f"eval_test_{i:03d}",
                started_at=f"2026-02-0{i+1}T12:00:00Z",
                completed_at=f"2026-02-0{i+1}T12:01:00Z",
                status="COMPLETED",
                total=10 + i,
                evaluated=10 + i,
                eligible=i,
            )
            save_run(run)

        summaries = list_runs(limit=10)
        assert len(summaries) == 3
        # Should be newest first (by file modification time)
        assert all(isinstance(s, EvaluationRunSummary) for s in summaries)

    def test_list_runs_respects_limit(self, temp_evaluations_dir):
        """List runs respects the limit parameter."""
        for i in range(5):
            run = EvaluationRunFull(
                run_id=f"eval_limit_test_{i:03d}",
                started_at=f"2026-02-0{i+1}T12:00:00Z",
                status="COMPLETED",
            )
            save_run(run)

        summaries = list_runs(limit=2)
        assert len(summaries) == 2


class TestDeleteOldRuns:
    """Tests for cleaning up old runs."""

    def test_delete_old_runs(self, temp_evaluations_dir):
        """Delete old runs keeps only the most recent ones."""
        # Create 5 runs
        for i in range(5):
            run = EvaluationRunFull(
                run_id=f"eval_delete_test_{i:03d}",
                started_at=f"2026-02-0{i+1}T12:00:00Z",
                status="COMPLETED",
            )
            save_run(run)

        # Keep only 2
        deleted = delete_old_runs(keep_count=2)
        assert deleted == 3

        # Verify only 2 remain
        remaining = list_runs()
        assert len(remaining) == 2


class TestCreateRunFromEvaluation:
    """Tests for converting UniverseEvaluationResult to EvaluationRunFull."""

    def test_create_run_from_evaluation(self):
        """Convert a UniverseEvaluationResult to EvaluationRunFull."""
        from app.core.eval.universe_evaluator import (
            UniverseEvaluationResult,
            SymbolEvaluationResult,
            Alert,
            CandidateTrade,
        )

        # Create a mock evaluation result
        sym_result = SymbolEvaluationResult(
            symbol="AAPL",
            source="ORATS",
            price=150.0,
            verdict="ELIGIBLE",
            primary_reason="All checks passed",
            score=85,
            regime="BULL",
            risk="LOW",
            liquidity_ok=True,
            options_available=True,
            candidate_trades=[
                CandidateTrade(
                    strategy="CSP",
                    expiry="2026-03-01",
                    strike=145.0,
                    delta=-0.25,
                )
            ],
        )

        alert = Alert(
            id="test_alert",
            type="ELIGIBLE",
            symbol="AAPL",
            message="AAPL is eligible",
            severity="INFO",
            created_at="2026-02-03T12:00:00Z",
        )

        eval_result = UniverseEvaluationResult(
            evaluation_state="COMPLETED",
            evaluation_state_reason="Completed successfully",
            last_evaluated_at="2026-02-03T12:01:00Z",
            duration_seconds=60.0,
            total=10,
            evaluated=10,
            eligible=1,
            shortlisted=1,
            symbols=[sym_result],
            alerts=[alert],
        )

        run = create_run_from_evaluation(
            run_id="eval_test_convert",
            started_at="2026-02-03T12:00:00Z",
            evaluation_result=eval_result,
            market_phase="OPEN",
        )

        assert run.run_id == "eval_test_convert"
        assert run.status == "COMPLETED"
        assert run.total == 10
        assert run.eligible == 1
        assert run.market_phase == "OPEN"
        assert len(run.symbols) == 1
        assert run.symbols[0]["symbol"] == "AAPL"
        assert run.symbols[0]["verdict"] == "ELIGIBLE"
        assert len(run.top_candidates) == 1
        assert len(run.alerts) == 1


class TestAPIResponseBuilders:
    """Tests for API response builder functions."""

    def test_build_latest_response_no_runs(self, temp_evaluations_dir):
        """Build latest response when no runs exist."""
        response = build_latest_response()
        assert response["has_completed_run"] is False
        assert response["run_id"] is None
        assert response["status"] == "NO_RUNS"

    def test_build_latest_response_with_run(self, temp_evaluations_dir):
        """Build latest response with a completed run."""
        run = EvaluationRunFull(
            run_id="eval_api_test",
            started_at="2026-02-03T12:00:00Z",
            completed_at="2026-02-03T12:01:00Z",
            status="COMPLETED",
            total=20,
            evaluated=20,
            eligible=5,
            shortlisted=2,
            top_candidates=[{"symbol": "AAPL", "score": 90}],
        )
        save_run(run)
        update_latest_pointer(run.run_id, run.completed_at)

        response = build_latest_response()
        assert response["has_completed_run"] is True
        assert response["run_id"] == "eval_api_test"
        assert response["counts"]["eligible"] == 5
        assert len(response["top_candidates"]) == 1

    def test_build_runs_list_response(self, temp_evaluations_dir):
        """Build runs list response."""
        run = EvaluationRunFull(
            run_id="eval_list_test",
            started_at="2026-02-03T12:00:00Z",
            status="COMPLETED",
        )
        save_run(run)
        update_latest_pointer(run.run_id, "2026-02-03T12:01:00Z")

        response = build_runs_list_response(limit=10)
        assert response["count"] == 1
        assert response["latest_run_id"] == "eval_list_test"
        assert len(response["runs"]) == 1

    def test_build_run_detail_response_found(self, temp_evaluations_dir):
        """Build run detail response for existing run."""
        run = EvaluationRunFull(
            run_id="eval_detail_test",
            started_at="2026-02-03T12:00:00Z",
            status="COMPLETED",
            total=15,
        )
        save_run(run)

        response = build_run_detail_response("eval_detail_test")
        assert response["found"] is True
        assert response["run_id"] == "eval_detail_test"
        assert response["total"] == 15

    def test_build_run_detail_response_not_found(self, temp_evaluations_dir):
        """Build run detail response for nonexistent run."""
        response = build_run_detail_response("nonexistent")
        assert response["found"] is False
        assert response["run_id"] == "nonexistent"


class TestRunRecordLifecycle:
    """End-to-end tests for run record lifecycle."""

    def test_complete_lifecycle(self, temp_evaluations_dir):
        """Test complete lifecycle: create, save, update pointer, load."""
        # 1. Generate run ID
        run_id = generate_run_id()
        assert run_id.startswith("eval_")

        # 2. Create initial run (RUNNING)
        run = EvaluationRunFull(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="RUNNING",
            total=25,
        )
        save_run(run)

        # 3. Update run to COMPLETED
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc).isoformat()
        run.evaluated = 25
        run.eligible = 8
        run.shortlisted = 3
        run.duration_seconds = 45.2
        save_run(run)

        # 4. Update latest pointer
        update_latest_pointer(run_id, run.completed_at)

        # 5. Verify latest pointer updated
        pointer = load_latest_pointer()
        assert pointer is not None
        assert pointer.run_id == run_id

        # 6. Verify latest run loads correctly
        latest = load_latest_run()
        assert latest is not None
        assert latest.run_id == run_id
        assert latest.status == "COMPLETED"
        assert latest.eligible == 8

        # 7. Verify API response
        response = build_latest_response()
        assert response["has_completed_run"] is True
        assert response["run_id"] == run_id
        assert response["counts"]["eligible"] == 8


class TestReasonPropagation:
    """Tests that reason codes propagate through the evaluation output schema."""

    def test_reason_in_run_symbols(self, temp_evaluations_dir):
        """Verify reason fields propagate to run symbols."""
        from app.core.eval.universe_evaluator import (
            UniverseEvaluationResult,
            SymbolEvaluationResult,
        )

        sym = SymbolEvaluationResult(
            symbol="TEST",
            verdict="HOLD",
            primary_reason="DATA_INCOMPLETE - missing: bid, ask",
            data_completeness=0.5,
            missing_fields=["bid", "ask"],
            data_quality_details={"price": "VALID", "bid": "MISSING", "ask": "MISSING"},
        )

        eval_result = UniverseEvaluationResult(
            evaluation_state="COMPLETED",
            evaluation_state_reason="Completed",
            total=1,
            evaluated=1,
            symbols=[sym],
        )

        run = create_run_from_evaluation(
            run_id="eval_reason_test",
            started_at="2026-02-03T12:00:00Z",
            evaluation_result=eval_result,
        )

        assert len(run.symbols) == 1
        assert "DATA_INCOMPLETE" in run.symbols[0]["primary_reason"]
        assert run.symbols[0]["data_completeness"] == 0.5
        assert "bid" in run.symbols[0]["missing_fields"]
        assert run.symbols[0]["data_quality_details"]["bid"] == "MISSING"
