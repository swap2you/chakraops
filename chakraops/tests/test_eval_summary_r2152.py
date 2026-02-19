# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R21.5.2: Evaluation heartbeat/summary Slack post to daily channel + throttle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_process_run_completed_sends_eval_summary_once_and_updates_slack_status(tmp_path):
    """After mocked evaluation completion, SlackNotifier.send_eval_summary is called once for daily and slack_status daily gets payload_type EVAL_SUMMARY."""
    from app.core.alerts.alert_engine import process_run_completed
    from app.core.alerts.slack_status import get_slack_status

    run = MagicMock()
    run.run_id = "eval_20260220_120000_abc12345"
    run.status = "COMPLETED"
    run.completed_at = "2026-02-20T12:00:00+00:00"
    run.total = 10
    run.evaluated = 10
    run.eligible = 2
    run.symbols = [
        {"symbol": "NVDA", "verdict": "ELIGIBLE", "score": 75},
        {"symbol": "SPY", "verdict": "ELIGIBLE", "score": 65},
        {"symbol": "AAPL", "verdict": "HOLD", "score": 50},
        {"symbol": "X", "verdict": "BLOCKED", "score": 30},
    ]
    run.top_candidates = [
        {"symbol": "NVDA", "score": 75, "candidate_trades": [{"strategy": "CSP"}]},
        {"symbol": "SPY", "score": 65, "candidate_trades": [{"strategy": "CSP"}]},
    ]
    run.duration_seconds = 12.5
    run.primary_reason = None

    slack_status_path = tmp_path / "slack_status.json"
    send_eval_summary_calls = []

    with patch("app.core.alerts.slack_status._status_path", return_value=slack_status_path):
        with patch("app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary", side_effect=lambda ch, payload: send_eval_summary_calls.append((ch, payload)) or True):
            with patch("app.core.alerts.slack_notifier.SlackNotifier.send", return_value=False):
                process_run_completed(run)

    assert len(send_eval_summary_calls) == 1
    ch, payload = send_eval_summary_calls[0]
    assert ch == "daily"
    assert payload.get("payload_type") == "EVAL_SUMMARY"
    assert payload.get("run_id") == run.run_id
    assert payload.get("total") == 10
    assert payload.get("eligible") == 2
    assert payload.get("blocked") == 1

    # Verify that when send_eval_summary actually runs, slack_status is updated with payload_type EVAL_SUMMARY
    with patch("app.core.alerts.slack_status._status_path", return_value=slack_status_path):
        with patch("app.core.alerts.slack_dispatcher.get_webhook_for_channel", return_value="https://hooks.slack.com/daily"):
            with patch("app.core.alerts.slack_notifier.requests.post", return_value=MagicMock(status_code=200)):
                from app.core.alerts.slack_notifier import SlackNotifier
                notifier = SlackNotifier({})
                notifier.send_eval_summary("daily", payload)
        status = get_slack_status()
    assert "daily" in status.get("channels", {})
    assert status["channels"]["daily"].get("last_payload_type") == "EVAL_SUMMARY"


def test_eval_summary_throttle_every_n_ticks():
    """With EVAL_SUMMARY_EVERY_N_TICKS=2, only every second scheduler tick sends summary."""
    from app.core.alerts.eval_summary import (
        set_scheduler_tick_for_run,
        get_scheduler_tick_for_run,
        should_send_eval_summary_this_run,
    )

    set_scheduler_tick_for_run("run_1", 1)
    set_scheduler_tick_for_run("run_2", 2)
    set_scheduler_tick_for_run("run_3", 3)

    with patch.dict("os.environ", {"EVAL_SUMMARY_EVERY_N_TICKS": "2"}, clear=False):
        assert should_send_eval_summary_this_run("run_1") is False
        assert should_send_eval_summary_this_run("run_2") is True
        assert should_send_eval_summary_this_run("run_3") is False

    # Force run (no tick) always sends
    assert get_scheduler_tick_for_run("run_force") is None
    with patch.dict("os.environ", {"EVAL_SUMMARY_EVERY_N_TICKS": "2"}, clear=False):
        assert should_send_eval_summary_this_run("run_force") is True
