"""Tests for Slack exclusion summary (Phase 7.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.execution.execution_gate import ExecutionGateResult
from app.execution.execution_plan import ExecutionPlan
from app.notifications.slack_notifier import send_decision_alert
from app.signals.decision_snapshot import DecisionSnapshot


@patch("app.notifications.slack_notifier.requests.post")
def test_slack_exclusions_summary_blocked(mock_post: MagicMock) -> None:
    """Test that exclusion summary is included in Slack message when blocked (Phase 7.2)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    snapshot = DecisionSnapshot(
        as_of="2026-01-28T10:00:00",
        universe_id_or_hash="phase2_default",
        stats={"total_candidates": 0, "total_exclusions": 5},
        candidates=[],
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        exclusions=[
            {"symbol": "AAPL", "rule": "NO_OPTIONS_FOR_SYMBOL", "message": "No options", "stage": "NORMALIZATION"},
            {"symbol": "AAPL", "rule": "NO_OPTIONS_FOR_SYMBOL", "message": "No options", "stage": "NORMALIZATION"},
            {"symbol": "MSFT", "rule": "NO_EXPIRY_IN_DTE_WINDOW", "message": "No expiry", "stage": "CSP_GENERATION"},
            {"symbol": "GOOGL", "rule": "NO_LIQUID_PUTS", "message": "No liquid", "stage": "CSP_GENERATION"},
            {"symbol": "GOOGL", "rule": "NO_LIQUID_PUTS", "message": "No liquid", "stage": "CSP_GENERATION"},
        ],
    )
    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS"])
    execution_plan = ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        send_decision_alert(snapshot, gate_result, execution_plan)

    # Verify request was made
    assert mock_post.called
    call_args = mock_post.call_args
    
    # Verify payload contains exclusion summary
    payload = call_args[1]["json"]
    message = payload["text"]
    assert "BLOCKED" in message
    assert "NO_SELECTED_SIGNALS" in message
    assert "Top Exclusion Rules:" in message
    assert "NO_OPTIONS_FOR_SYMBOL: 2 occurrence(s)" in message
    assert "NO_LIQUID_PUTS: 2 occurrence(s)" in message
    assert "NO_EXPIRY_IN_DTE_WINDOW: 1 occurrence(s)" in message


@patch("app.notifications.slack_notifier.requests.post")
def test_slack_exclusions_summary_no_exclusions(mock_post: MagicMock) -> None:
    """Test that exclusion summary is not included when exclusions are None."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    snapshot = DecisionSnapshot(
        as_of="2026-01-28T10:00:00",
        universe_id_or_hash="phase2_default",
        stats={"total_candidates": 0},
        candidates=[],
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
        exclusions=None,  # No exclusions
    )
    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS"])
    execution_plan = ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        send_decision_alert(snapshot, gate_result, execution_plan)

    # Verify request was made
    assert mock_post.called
    call_args = mock_post.call_args
    
    # Verify payload does NOT contain exclusion summary
    payload = call_args[1]["json"]
    message = payload["text"]
    assert "BLOCKED" in message
    assert "Top Exclusion Rules:" not in message
