# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.2: ORATS freshness state (OK / DELAYED / WARN / ERROR)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


def test_get_orats_freshness_state_ok():
    """When effective_last_success is within OK window, state is OK; includes as_of and threshold_triggered."""
    from app.api.data_health import get_orats_freshness_state
    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with patch("app.api.data_health._get_effective_orats_timestamp", return_value=(recent, "test", "test")):
        with patch("app.api.data_health._LAST_ERROR_AT", None):
            state = get_orats_freshness_state()
    assert state.get("state") == "OK"
    assert state.get("state_label") == "OK"
    assert state.get("as_of") == recent
    assert state.get("threshold_triggered") == "ok_minutes"


def test_get_orats_freshness_state_delayed():
    """When age is between OK and WARN threshold, state is DELAYED."""
    from app.api.data_health import get_orats_freshness_state
    delayed = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    with patch("app.api.data_health._get_effective_orats_timestamp", return_value=(delayed, "test", "test")):
        with patch("app.api.data_health._LAST_ERROR_AT", None):
            state = get_orats_freshness_state()
    assert state.get("state") == "DELAYED"
    assert "DELAYED" in (state.get("state_label") or "")


def test_get_orats_freshness_state_warn():
    """When age is beyond WARN threshold, state is WARN."""
    from app.api.data_health import get_orats_freshness_state
    stale = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    with patch("app.api.data_health._get_effective_orats_timestamp", return_value=(stale, "test", "test")):
        with patch("app.api.data_health._LAST_ERROR_AT", None):
            state = get_orats_freshness_state()
    assert state.get("state") == "WARN"
    assert state.get("state_label") == "WARN"


def test_get_orats_freshness_state_error_when_no_timestamp():
    """When no effective timestamp and last error set, state is ERROR; threshold_triggered is error."""
    from app.api.data_health import get_orats_freshness_state
    with patch("app.api.data_health._get_effective_orats_timestamp", return_value=(None, "test", "test")):
        with patch("app.api.data_health._LAST_ERROR_AT", "2026-01-01T12:00:00Z"):
            state = get_orats_freshness_state()
    assert state.get("state") == "ERROR"
    assert state.get("state_label") == "ERROR"
    assert state.get("as_of") is None
    assert state.get("threshold_triggered") == "error"


def test_system_health_includes_orats_freshness_state():
    """GET /api/ui/system-health orats block includes orats_freshness_state, label, as_of, threshold_triggered."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app
    client = TestClient(app)
    r = client.get("/api/ui/system-health")
    if r.status_code == 401:
        pytest.skip("UI key required")
    assert r.status_code == 200
    orats = r.json().get("orats") or {}
    assert "orats_freshness_state" in orats
    assert "orats_freshness_state_label" in orats
    assert orats["orats_freshness_state"] in ("OK", "DELAYED", "WARN", "ERROR", "UNKNOWN")
    assert "orats_as_of" in orats
    assert "orats_threshold_triggered" in orats


def test_system_health_slack_channels_r222():
    """R22.2: GET system-health slack.channels has signals, daily, data_health, critical with last_send_at, last_send_ok, last_error, last_payload_type."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app
    client = TestClient(app)
    r = client.get("/api/ui/system-health")
    if r.status_code == 401:
        pytest.skip("UI key required")
    assert r.status_code == 200
    slack = r.json().get("slack") or {}
    channels = slack.get("channels") or {}
    for ch in ("signals", "daily", "data_health", "critical"):
        assert ch in channels, f"missing channel {ch}"
        c = channels[ch]
        assert "last_send_at" in c
        assert "last_send_ok" in c
        assert "last_error" in c
        assert "last_payload_type" in c
