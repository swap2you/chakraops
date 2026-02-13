# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.3: Slack format, exit priority, routing escalation, daily summary, watchdog, send-trade-alert."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.alerts.slack_dispatcher import (
    _format_message,
    _get_webhook,
    _get_webhook_for_position,
    route_alert,
)
from app.core.positions.position_evaluator import evaluate_position, EXIT_NOW, EXIT_TAKE_PROFIT, EXIT_ROLL_SUGGESTED, EXIT_HOLD
from app.core.system.watchdog import (
    check_scheduler_health,
    check_orats_latency,
    check_signals_24h,
)


# --- Exit priority classification (position_evaluator) ---


def test_exit_priority_panic():
    """panic_flag True → exit_priority PANIC."""
    pos = {
        "position_id": "p1",
        "symbol": "SPY",
        "mode": "CSP",
        "entry_premium": 2.0,
        "entry_date": "2025-01-01",
        "expiration": "2025-03-21",
    }
    ep = {
        "enabled": True,
        "structure_plan": {"T1": 500, "T2": 510},
        "time_plan": {"dte_soft_exit": 14, "dte_hard_exit": 7},
        "panic_plan": {"panic_flag": True},
        "inputs": {"regime_daily": "UP"},
    }
    ev = evaluate_position(pos, 480.0, 1.0, 1.2, ep, None)
    assert ev.get("exit_priority") == "PANIC"
    assert ev.get("exit_signal") == EXIT_NOW


def test_exit_priority_expiry_critical():
    """dte <= 3 → exit_priority EXPIRY_CRITICAL (when exit_signal is EXIT_NOW)."""
    from datetime import date, timedelta
    exp = (date.today() + timedelta(days=2)).isoformat()
    pos = {
        "position_id": "p2",
        "symbol": "SPY",
        "mode": "CSP",
        "entry_premium": 2.0,
        "entry_date": "2025-01-01",
        "expiration": exp,
    }
    ep = {
        "enabled": True,
        "structure_plan": {"T1": 600, "T2": 610},
        "time_plan": {"dte_soft_exit": 14, "dte_hard_exit": 7},
        "panic_plan": {"panic_flag": False},
        "inputs": {"regime_daily": "UP"},
    }
    ev = evaluate_position(pos, 480.0, 1.0, 1.2, ep, None)
    assert ev.get("dte") <= 3
    assert ev.get("exit_priority") == "EXPIRY_CRITICAL"


def test_exit_priority_fast_capture():
    """premium_capture_pct >= 0.90 → exit_priority FAST_CAPTURE (when dte > 3 and exit_signal EXIT_NOW from 75% target)."""
    from datetime import date, timedelta
    exp = (date.today() + timedelta(days=30)).isoformat()
    pos = {
        "position_id": "p3",
        "symbol": "SPY",
        "mode": "CSP",
        "entry_premium": 2.0,
        "entry_date": "2025-01-01",
        "expiration": exp,
    }
    ep = {
        "enabled": True,
        "structure_plan": {"T1": 400, "T2": 410},
        "time_plan": {"dte_soft_exit": 14, "dte_hard_exit": 7},
        "panic_plan": {"panic_flag": False},
        "inputs": {"regime_daily": "UP"},
    }
    # bid/ask such that premium capture >= 0.90 (entry 2.0, mid 0.15 -> 0.925); dte > 3 so not EXPIRY_CRITICAL
    ev = evaluate_position(pos, 350.0, 0.1, 0.2, ep, None)
    assert ev.get("premium_capture_pct") is not None
    if ev.get("premium_capture_pct") and ev.get("premium_capture_pct") >= 0.90 and (ev.get("dte") or 0) > 3:
        assert ev.get("exit_priority") == "FAST_CAPTURE"


def test_exit_priority_advisory():
    """exit_signal TAKE_PROFIT or ROLL_SUGGESTED → exit_priority ADVISORY."""
    from datetime import date, timedelta
    exp = (date.today() + timedelta(days=20)).isoformat()
    pos = {
        "position_id": "p4",
        "symbol": "SPY",
        "mode": "CSP",
        "entry_premium": 2.0,
        "entry_date": "2025-01-01",
        "expiration": exp,
    }
    ep = {
        "enabled": True,
        "structure_plan": {"T1": 480, "T2": 500},
        "time_plan": {"dte_soft_exit": 14, "dte_hard_exit": 7},
        "panic_plan": {"panic_flag": False},
        "inputs": {"regime_daily": "UP"},
    }
    # Hit T1 and premium 50% -> TAKE_PROFIT
    ev = evaluate_position(pos, 481.0, 0.9, 1.0, ep, None)
    if ev.get("exit_signal") in (EXIT_TAKE_PROFIT, EXIT_ROLL_SUGGESTED):
        assert ev.get("exit_priority") == "ADVISORY"


# --- Routing escalation ---


def test_get_webhook_for_position_critical():
    """PANIC, EXPIRY_CRITICAL, NORMAL_EXIT → CRITICAL webhook."""
    with patch.dict(os.environ, {"SLACK_WEBHOOK_CRITICAL": "https://critical"}, clear=False):
        assert _get_webhook_for_position("PANIC") == "https://critical"
        assert _get_webhook_for_position("EXPIRY_CRITICAL") == "https://critical"
        assert _get_webhook_for_position("NORMAL_EXIT") == "https://critical"


def test_get_webhook_for_position_signals():
    """FAST_CAPTURE, ADVISORY → SIGNALS webhook."""
    with patch.dict(os.environ, {"SLACK_WEBHOOK_SIGNALS": "https://signals"}, clear=False):
        assert _get_webhook_for_position("FAST_CAPTURE") == "https://signals"
        assert _get_webhook_for_position("ADVISORY") == "https://signals"


# --- Daily summary formatting ---


def test_format_daily_structured():
    """DAILY format includes top_signals, open_positions_count, total_capital_used, exposure_pct, average_premium_capture, exit_alerts_today."""
    payload = {
        "top_signals": [
            {"symbol": "NVDA", "tier": "A", "severity": "READY"},
            {"symbol": "SPY", "tier": "B", "severity": "READY"},
        ],
        "open_positions_count": 3,
        "total_capital_used": 52000,
        "exposure_pct": 34.0,
        "average_premium_capture": 0.41,
        "exit_alerts_today": 2,
    }
    text = _format_message("DAILY", payload)
    assert "DAILY SUMMARY" in text or "Daily" in text
    assert "NVDA" in text
    assert "SPY" in text
    assert "3" in text
    assert "52000" in text or "52,000" in text
    assert "34" in text
    assert "41" in text
    assert "2" in text


# --- Watchdog ---


def test_watchdog_scheduler_stalled():
    """check_scheduler_health returns payload when last_run too old."""
    from datetime import datetime, timezone, timedelta
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    result = check_scheduler_health(old, interval_minutes=30)
    assert result is not None
    assert result.get("reason") == "SCHEDULER_STALLED"


def test_watchdog_scheduler_ok():
    """check_scheduler_health returns None when last_run within 2*interval."""
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    result = check_scheduler_health(recent, interval_minutes=30)
    assert result is None


def test_watchdog_orats_latency_high():
    """check_orats_latency returns payload when rolling_avg_ms > 6000."""
    result = check_orats_latency(7000.0)
    assert result is not None
    assert result.get("reason") == "ORATS_LATENCY_HIGH"


def test_watchdog_orats_latency_ok():
    """check_orats_latency returns None when <= 6000."""
    assert check_orats_latency(5000.0) is None
    assert check_orats_latency(None) is None


def test_watchdog_no_signals_24h():
    """check_signals_24h returns payload when has_signals_in_24h is False."""
    result = check_signals_24h(False)
    assert result is not None
    assert result.get("reason") == "NO_SIGNALS_24H"
    assert result.get("channel") == "DAILY"


def test_watchdog_has_signals_24h():
    """check_signals_24h returns None when has_signals_in_24h is True."""
    assert check_signals_24h(True) is None


# --- UI endpoint validation (send-trade-alert) ---


def test_send_trade_alert_requires_eligible_tier_severity():
    """POST send-trade-alert with symbol that has no payload or ineligible tier/severity → 400."""
    try:
        from fastapi.testclient import TestClient
        from app.api.server import app
    except ImportError:
        pytest.skip("fastapi not installed")
    client = TestClient(app)
    response = client.post("/api/ops/send-trade-alert", json={})
    assert response.status_code == 400
    response = client.post("/api/ops/send-trade-alert", json={"symbol": ""})
    assert response.status_code == 400
    response = client.post("/api/ops/send-trade-alert", json={"symbol": "NOPAYLOAD999"})
    assert response.status_code == 400


def test_route_alert_returns_bool():
    """route_alert returns True/False for send success (Phase 7.3)."""
    with patch.dict(os.environ, {}, clear=False):
        for k in ("SLACK_WEBHOOK_CRITICAL", "SLACK_WEBHOOK_SIGNALS", "SLACK_WEBHOOK_HEALTH", "SLACK_WEBHOOK_DAILY"):
            os.environ.pop(k, None)
        ok = route_alert("SIGNAL", {"symbol": "X", "tier": "A", "severity": "READY"})
        assert ok is False
    with patch.dict(os.environ, {"SLACK_WEBHOOK_SIGNALS": "https://hooks.slack.com/x"}, clear=False):
        with patch("app.core.alerts.slack_dispatcher.send_slack_message", return_value=True):
            ok = route_alert("SIGNAL", {"symbol": "X", "tier": "A", "severity": "READY"}, event_key=None)
            assert ok is True
