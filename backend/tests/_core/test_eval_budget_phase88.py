# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.8: Evaluation Budget."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.eval.evaluation_budget import EvaluationBudget


def test_budget_trim_symbols():
    """trim_symbols enforces max_symbols."""
    now = datetime.now(timezone.utc)
    budget = EvaluationBudget(
        max_wall_time_sec=240,
        max_symbols=5,
        max_requests_estimate=1000,
        started_at=now,
    )
    symbols = ["A", "B", "C", "D", "E", "F", "G"]
    trimmed = budget.trim_symbols(symbols)
    assert len(trimmed) == 5
    assert trimmed == ["A", "B", "C", "D", "E"]


def test_budget_stops_on_time():
    """should_stop_for_time True when elapsed >= max_wall_time_sec."""
    now = datetime.now(timezone.utc)
    budget = EvaluationBudget(
        max_wall_time_sec=1,
        max_symbols=25,
        max_requests_estimate=1000,
        started_at=now - timedelta(seconds=2),
    )
    assert budget.should_stop_for_time() is True
    assert budget.can_continue() is False


def test_budget_status_counters():
    """budget_status returns counters."""
    now = datetime.now(timezone.utc)
    budget = EvaluationBudget(
        max_wall_time_sec=240,
        max_symbols=25,
        max_requests_estimate=1000,
        started_at=now,
    )
    budget.record_batch(10, requests_estimate=30)  # explicit requests_estimate
    budget.record_batch(5, requests_estimate=15)
    status = budget.budget_status()
    assert status["symbols_processed"] == 15
    assert status["requests_estimated"] == 45
    assert status["batches_processed"] == 2
    assert "elapsed_sec" in status
    assert status["time_exceeded"] is False
