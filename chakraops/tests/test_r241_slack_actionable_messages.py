# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.1: Actionable Slack — builder fields, forbidden substrings, dedupe."""

from pathlib import Path

import pytest

from app.core.alerts.slack_dispatcher import (
    build_actionable_message_r241,
    FORBIDDEN_IN_SLACK,
    _sanitize_slack_text,
    _actionable_dedupe_key,
    should_send_actionable_message,
)


def test_r241_message_required_fields():
    """R24.1 message includes symbol, strategy, next_action, rationale when provided."""
    payload = {
        "symbol": "SPY",
        "strategy": "CSP",
        "next_action_code": "ENTRY",
        "rationale_lines": ["Eligible for entry; no open position."],
        "next_action_details": {"key_numbers": {"spot": 450.0, "delta_best": 0.29, "dte": 35}},
        "contract_key": "SPY_20260320_C_450",
        "suggested_contracts": 2,
        "required_cash": 45000,
    }
    text = build_actionable_message_r241(payload)
    assert "SPY" in text
    assert "CSP" in text
    assert "ENTRY" in text
    assert "Eligible" in text or "entry" in text
    assert "450" in text
    assert "0.29" in text or "0.29" in text
    assert "SPY_20260320" in text or "Contract" in text


def test_r241_message_never_forbidden():
    """R24.1 message must not contain any FORBIDDEN_IN_SLACK substring."""
    payload = {
        "symbol": "X",
        "rationale_lines": ["FAIL_foo", "WARN_bar", "api_key leak", "token x", "traceback", "File \"/path\""],
    }
    text = build_actionable_message_r241(payload)
    for f in FORBIDDEN_IN_SLACK:
        assert f not in text, "Message must not contain %r" % f


def test_sanitize_removes_forbidden():
    """_sanitize_slack_text removes all forbidden substrings."""
    raw = "Hello FAIL_xyz WARN_abc api_key token traceback"
    out = _sanitize_slack_text(raw)
    assert "FAIL_" not in out
    assert "WARN_" not in out
    assert "api_key" not in out
    assert "token" not in out


def test_actionable_dedupe_key_deterministic():
    """Dedupe key is deterministic for same inputs."""
    k1 = _actionable_dedupe_key("SPY", "OPTIONS", "ENTRY", "SPY_C_450", "2")
    k2 = _actionable_dedupe_key("SPY", "OPTIONS", "ENTRY", "SPY_C_450", "2")
    assert k1 == k2
    assert "actionable|" in k1
    assert "SPY" in k1


def test_dedupe_suppresses_repeat_allows_when_action_changes(tmp_path):
    """Dedupe suppresses same message within N min; allows when action changes (different key)."""
    state_file = tmp_path / "dedupe.json"
    # First send: allowed
    ok1 = should_send_actionable_message(
        "WMT", "OPTIONS", "ENTRY", "WMT_C_150", "2",
        state_path=state_file, throttle_minutes=15,
    )
    assert ok1 is True
    # Same key within 15 min: suppressed
    ok2 = should_send_actionable_message(
        "WMT", "OPTIONS", "ENTRY", "WMT_C_150", "2",
        state_path=state_file, throttle_minutes=15,
    )
    assert ok2 is False
    # Different action (different key): allowed
    ok3 = should_send_actionable_message(
        "WMT", "OPTIONS", "CLOSE", "WMT_C_150", "2",
        state_path=state_file, throttle_minutes=15,
    )
    assert ok3 is True
