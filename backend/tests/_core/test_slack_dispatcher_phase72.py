# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.2: Slack dispatcher — routing, dedup, no crash when webhook missing."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.alerts.slack_dispatcher import (
    _get_webhook,
    _state_hash,
    route_alert,
    send_slack_message,
    should_send_alert,
    DEFAULT_STATE_PATH,
)


def test_missing_webhook_does_not_crash():
    """No webhook env set → route_alert returns without raising."""
    with patch.dict(os.environ, {}, clear=False):
        for key in ("SLACK_WEBHOOK_CRITICAL", "SLACK_WEBHOOK_SIGNALS", "SLACK_WEBHOOK_HEALTH", "SLACK_WEBHOOK_DAILY"):
            os.environ.pop(key, None)
        route_alert("SIGNAL", {"symbol": "SPY", "tier": "B", "severity": "READY"})
        route_alert("CRITICAL", {"symbol": "SPY", "position_id": "uuid", "exit_signal": "EXIT_NOW"})
        route_alert("HEALTH", {"failed_symbols": ["X"]})
        route_alert("DAILY", {"top_count": 5})


def test_dedup_identical_state_suppresses_send(tmp_path: Path):
    """Same event_key + same state hash → should_send_alert False second time."""
    state_path = tmp_path / "last_sent_state.json"
    payload = {"symbol": "SPY", "tier": "A"}
    h = _state_hash(payload)
    first = should_send_alert("signal:SPY", h, state_path)
    second = should_send_alert("signal:SPY", h, state_path)
    assert first is True
    assert second is False


def test_dedup_state_hash_changes_trigger_send(tmp_path: Path):
    """Different state hash for same event_key → should_send_alert True again."""
    state_path = tmp_path / "last_sent_state.json"
    assert should_send_alert("signal:SPY", _state_hash({"symbol": "SPY", "tier": "A"}), state_path) is True
    assert should_send_alert("signal:SPY", _state_hash({"symbol": "SPY", "tier": "A"}), state_path) is False
    assert should_send_alert("signal:SPY", _state_hash({"symbol": "SPY", "tier": "B"}), state_path) is True


def test_routing_chooses_correct_webhook():
    """_get_webhook returns correct env var per event_type."""
    with patch.dict(os.environ, {}, clear=False):
        for k in ("SLACK_WEBHOOK_CRITICAL", "SLACK_WEBHOOK_SIGNALS", "SLACK_WEBHOOK_HEALTH", "SLACK_WEBHOOK_DAILY"):
            os.environ.pop(k, None)
        assert _get_webhook("CRITICAL") is None
        assert _get_webhook("SIGNAL") is None
        os.environ["SLACK_WEBHOOK_SIGNALS"] = "https://hooks.slack.com/signals"
        assert _get_webhook("SIGNAL") == "https://hooks.slack.com/signals"
        os.environ["SLACK_WEBHOOK_CRITICAL"] = "https://hooks.slack.com/critical"
        assert _get_webhook("CRITICAL") == "https://hooks.slack.com/critical"


def test_send_slack_message_returns_false_on_empty():
    """Empty webhook or text → False, no request."""
    assert send_slack_message("", "hello") is False
    assert send_slack_message("https://x", "") is False


def test_send_slack_message_handles_exception():
    """Exceptions in POST → return False, no raise."""
    with patch("app.core.alerts.slack_dispatcher._requests") as mock_req:
        if mock_req is None:
            pytest.skip("requests not installed")
        mock_req.post.side_effect = Exception("network error")
        result = send_slack_message("https://hooks.slack.com/fake", "test")
    assert result is False
