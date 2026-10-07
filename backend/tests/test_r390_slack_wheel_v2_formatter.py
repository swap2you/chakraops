# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R39: Slack wheel_v2 formatter — render-only, dedupe preserved."""

from __future__ import annotations

from pathlib import Path

from app.core.alerts.slack_wheel_v2_formatter import (
    format_wheel_v2_slack_message,
    prepare_wheel_v2_slack_send,
    should_send_wheel_v2_slack,
)
from app.core.decision_engine.wheel_v2.slack_payload import to_slack_ready_payload


def _sample_payload(**over):
    base = {
        "symbol": "AAPL",
        "phase": "CSP_ENTRY",
        "phase_label": "Cash-secured put entry",
        "strategy": "CSP",
        "action": "OPEN_CSP",
        "action_label": "Open cash-secured put",
        "plan_summary": "Strike 180 · Expiry 2026-09-18 · DTE 35",
        "arbitration_labels": ["Prefer CSP over shares"],
        "manual_only": True,
        "trade_execution": False,
        "render_only": True,
    }
    base.update(over)
    return base


def test_format_wheel_v2_message_structure():
    text = format_wheel_v2_slack_message(_sample_payload())
    assert "Wheel advisory" in text
    assert "AAPL" in text
    assert "Open cash-secured put" in text
    assert "Manual execution only" in text
    assert "FAIL_" not in text
    assert "WARN_" not in text


def test_format_consumes_to_slack_ready_payload():
    ready = to_slack_ready_payload(
        {
            "symbol": "MSFT",
            "phase": "HOLD",
            "strategy": "CSP",
            "action": "HOLD",
            "manual_plan": {"summary_label": "Hold position"},
            "arbitration": {},
        }
    )
    text = format_wheel_v2_slack_message(ready)
    assert "MSFT" in text
    assert "Hold" in text


def test_format_sanitizes_forbidden_tokens():
    text = format_wheel_v2_slack_message(
        _sample_payload(plan_summary="Review FAIL_DATA issue", arbitration_labels=["WARN_STALE"])
    )
    assert "FAIL_" not in text
    assert "WARN_" not in text


def test_dedupe_suppresses_repeat_send(tmp_path: Path):
    state = tmp_path / "dedupe.json"
    payload = _sample_payload()
    assert should_send_wheel_v2_slack(payload, state_path=state, throttle_minutes=60) is True
    assert should_send_wheel_v2_slack(payload, state_path=state, throttle_minutes=60) is False


def test_prepare_returns_none_when_deduped(tmp_path: Path):
    state = tmp_path / "dedupe2.json"
    payload = _sample_payload(symbol="XYZ")
    first = prepare_wheel_v2_slack_send(payload, state_path=state, throttle_minutes=60)
    assert first is not None
    assert first["manual_only"] is True
    assert first["render_only"] is True
    assert first["trade_execution"] is False
    assert "XYZ" in first["text"]
    second = prepare_wheel_v2_slack_send(payload, state_path=state, throttle_minutes=60)
    assert second is None
