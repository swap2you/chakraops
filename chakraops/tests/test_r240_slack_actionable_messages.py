# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.0: Actionable Slack messages — required fields present, no forbidden substrings."""

import pytest

from app.core.alerts.slack_dispatcher import (
    build_actionable_message_r240,
    _format_message,
    FORBIDDEN_IN_SLACK,
)


def test_actionable_message_contains_required_fields():
    """Actionable message includes symbol, strategy, and sizing when provided."""
    payload = {
        "symbol": "WMT",
        "strategy": "CSP",
        "expiry": "2026-03-20",
        "strike": 150.0,
        "delta": 0.30,
        "bid": 2.50,
        "ask": 2.70,
        "credit_estimate": 260.0,
        "suggested_contracts": 2,
        "required_cash": 30000.0,
        "reasons_safe": ["Near support", "Delta in band"],
    }
    text = build_actionable_message_r240(payload)
    assert "WMT" in text
    assert "CSP" in text
    assert "150" in text or "150.0" in text
    assert "0.30" in text or "0.3" in text
    assert "260" in text or "260.0" in text
    assert "2" in text
    assert "30000" in text or "30,000" in text
    assert "Near support" in text
    assert "Delta in band" in text


def test_actionable_message_never_contains_fail_warn():
    """Message must not contain FAIL_ or WARN_ substrings."""
    payload = {
        "symbol": "TEST",
        "reasons_safe": ["FAIL_SOMETHING", "WARN_OTHER"],
    }
    text = build_actionable_message_r240(payload)
    assert "FAIL_" not in text
    assert "WARN_" not in text


def test_actionable_message_never_contains_secrets():
    """Message must not contain api_key or token."""
    payload = {
        "symbol": "X",
        "reasons_safe": ["api_key is set", "token expired"],
    }
    text = build_actionable_message_r240(payload)
    assert "api_key" not in text
    assert "token" not in text


def test_format_message_signal_sanitized():
    """_format_message(SIGNAL) output has no forbidden patterns."""
    payload = {
        "symbol": "NVDA",
        "mode": "CSP",
        "tier": "A",
        "severity": "READY",
        "composite_score": 80,
        "strike": 175,
        "dte": 35,
        "delta": 0.34,
        "capital_required_estimate": 17500,
    }
    text = _format_message("SIGNAL", payload)
    for forbidden in FORBIDDEN_IN_SLACK:
        assert forbidden not in text, "Signal message must not contain %r" % forbidden


def test_format_message_daily_sanitized():
    """_format_message(DAILY) output has no forbidden patterns."""
    payload = {
        "top_signals": [{"symbol": "A", "tier": "A", "severity": "READY"}],
        "open_positions_count": 0,
        "total_capital_used": 0,
        "exposure_pct": 0,
        "exit_alerts_today": 0,
    }
    text = _format_message("DAILY", payload)
    for forbidden in FORBIDDEN_IN_SLACK:
        assert forbidden not in text
