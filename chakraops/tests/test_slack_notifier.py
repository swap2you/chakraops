"""Tests for Phase 7 Slack notification module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.execution.execution_gate import ExecutionGateResult
from app.execution.execution_plan import ExecutionPlan, ExecutionOrder
from app.notifications.slack_notifier import send_decision_alert, send_exit_alert
from app.signals.decision_snapshot import DecisionSnapshot
from app.market.drift_detector import DriftReason, DriftStatus, DriftItem


def test_send_decision_alert_blocked_no_webhook() -> None:
    """Test that missing webhook URL returns False (graceful; no exception)."""
    snapshot = DecisionSnapshot(
        as_of="2026-01-28T10:00:00",
        universe_id_or_hash="test",
        stats={"total_candidates": 0},
        candidates=[],
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
    )
    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS"])
    execution_plan = ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])

    with patch.dict("os.environ", {}, clear=True):
        result = send_decision_alert(snapshot, gate_result, execution_plan)
    assert result is False


@patch("app.notifications.slack_notifier.requests.post")
def test_send_decision_alert_blocked_with_reasons(mock_post: MagicMock) -> None:
    """Test Slack message formatting for blocked gate."""
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
    )
    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS", "SNAPSHOT_STALE"])
    execution_plan = ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        send_decision_alert(snapshot, gate_result, execution_plan)

    # Verify request was made
    assert mock_post.called
    call_args = mock_post.call_args
    
    # Verify URL
    assert call_args[0][0] == "https://hooks.slack.com/test"
    
    # Verify payload contains blocked status and reasons
    payload = call_args[1]["json"]
    message = payload["text"]
    assert "BLOCKED" in message
    assert "NO_SELECTED_SIGNALS" in message
    assert "SNAPSHOT_STALE" in message
    assert "Manual execution only" in message


@patch("app.notifications.slack_notifier.requests.post")
def test_send_decision_alert_allowed_with_signals(mock_post: MagicMock) -> None:
    """Test Slack message formatting for allowed gate with signals."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    # Create mock selected signals
    selected_signals = [
        {
            "scored": {
                "rank": 1,
                "score": {"total": 0.85},
                "candidate": {
                    "symbol": "AAPL",
                    "signal_type": "CSP",
                    "strike": 150.0,
                    "expiry": "2026-03-15",
                    "mid": 2.50,
                    "bid": 2.45,
                },
            }
        },
        {
            "scored": {
                "rank": 2,
                "score": {"total": 0.78},
                "candidate": {
                    "symbol": "MSFT",
                    "signal_type": "CC",
                    "strike": 400.0,
                    "expiry": "2026-03-15",
                    "mid": 3.20,
                    "bid": 3.15,
                },
            }
        },
    ]

    snapshot = DecisionSnapshot(
        as_of="2026-01-28T10:00:00",
        universe_id_or_hash="phase2_default",
        stats={"total_candidates": 10, "selected_signals": 2},
        candidates=[],
        scored_candidates=None,
        selected_signals=selected_signals,
        explanations=None,
    )
    gate_result = ExecutionGateResult(allowed=True, reasons=[])
    execution_plan = ExecutionPlan(
        allowed=True,
        blocked_reason=None,
        orders=[
            ExecutionOrder(
                symbol="AAPL",
                action="SELL_TO_OPEN",
                strike=150.0,
                expiry="2026-03-15",
                option_right="PUT",
                quantity=1,
                limit_price=2.50,
            ),
            ExecutionOrder(
                symbol="MSFT",
                action="SELL_TO_OPEN",
                strike=400.0,
                expiry="2026-03-15",
                option_right="CALL",
                quantity=1,
                limit_price=3.20,
            ),
        ],
    )

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        send_decision_alert(snapshot, gate_result, execution_plan)

    # Verify request was made
    assert mock_post.called
    call_args = mock_post.call_args
    
    # Verify payload contains allowed status and signals
    payload = call_args[1]["json"]
    message = payload["text"]
    assert "ALLOWED" in message
    assert "AAPL" in message
    assert "MSFT" in message
    assert "CSP" in message
    assert "CC" in message
    assert "$150" in message or "150.0" in message
    assert "$400" in message or "400.0" in message
    assert "Manual execution only" in message


@patch("app.notifications.slack_notifier.requests.post")
def test_send_decision_alert_with_file_path(mock_post: MagicMock) -> None:
    """Test that decision file path is included in message if provided."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    snapshot = DecisionSnapshot(
        as_of="2026-01-28T10:00:00",
        universe_id_or_hash="test",
        stats={"total_candidates": 0},
        candidates=[],
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
    )
    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS"])
    execution_plan = ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])
    decision_file = Path("out/decision_2026-01-28T10-00-00.json")

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        send_decision_alert(snapshot, gate_result, execution_plan, decision_file_path=decision_file)

    # Verify file path is in message
    call_args = mock_post.call_args
    payload = call_args[1]["json"]
    message = payload["text"]
    assert "decision_2026-01-28T10-00-00.json" in message


@patch("app.notifications.slack_notifier.requests.post")
def test_send_decision_alert_http_error(mock_post: MagicMock) -> None:
    """Test that HTTP errors are raised."""
    import requests
    
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    http_error = requests.HTTPError("HTTP 400")
    http_error.response = mock_response
    mock_response.raise_for_status = MagicMock(side_effect=http_error)
    mock_post.return_value = mock_response

    snapshot = DecisionSnapshot(
        as_of="2026-01-28T10:00:00",
        universe_id_or_hash="test",
        stats={"total_candidates": 0},
        candidates=[],
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
    )
    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS"])
    execution_plan = ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        with pytest.raises(ValueError, match="Slack webhook returned error"):
            send_decision_alert(snapshot, gate_result, execution_plan)


@patch("app.notifications.slack_notifier.requests.post")
def test_send_decision_alert_with_drift_status(mock_post: MagicMock) -> None:
    """Phase 8.2: When drift_status is provided, message includes drift block with severity."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    snapshot = DecisionSnapshot(
        as_of="2026-01-28T10:00:00",
        universe_id_or_hash="test",
        stats={"total_candidates": 0},
        candidates=[],
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
    )
    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS"])
    execution_plan = ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])
    drift_status = DriftStatus(
        has_drift=True,
        items=[
            DriftItem(DriftReason.PRICE_DRIFT, "AAPL", "Underlying price drifted 5%", snapshot_value=100.0, live_value=105.0),
        ],
    )

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        send_decision_alert(snapshot, gate_result, execution_plan, drift_status=drift_status)

    payload = mock_post.call_args[1]["json"]
    message = payload["text"]
    assert "Live Market Drift" in message
    assert "WARN" in message or "BLOCK" in message or "INFO" in message
    assert "PRICE_DRIFT" in message
    assert "AAPL" in message


def test_send_exit_alert_no_webhook() -> None:
    """When webhook is not set, send_exit_alert returns False (no exception)."""
    with patch.dict("os.environ", {}, clear=True):
        result = send_exit_alert("AAPL", 150.0, "STOP", detail="Underlying -20% below strike")
    assert result is False


@patch("app.notifications.slack_notifier.requests.post")
def test_send_exit_alert_sent(mock_post: MagicMock) -> None:
    """When webhook is set, send_exit_alert posts and returns True."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        result = send_exit_alert("AAPL", 150.0, "EXIT", detail="50% of max profit")

    assert result is True
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    message = payload["text"]
    assert "ChakraOps Exit Alert" in message
    assert "EXIT" in message
    assert "AAPL" in message
    assert "150" in message
    assert "50% of max profit" in message
