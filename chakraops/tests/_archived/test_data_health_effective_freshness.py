# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for ORATS data health effective freshness (persisted run vs live probe)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest


@patch("app.api.data_health._get_effective_orats_timestamp")
@patch("app.api.data_health._load_persisted_state")
def test_banner_uses_persisted_run_when_available(mock_load, mock_get_effective):
    """When latest completed evaluation run exists, status and effective_* use persisted run time."""
    mock_load.return_value = None
    recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    mock_get_effective.return_value = (recent, "persisted_run", "Using latest completed evaluation data")

    from app.api.data_health import get_data_health

    state = get_data_health()
    assert state["effective_last_success_at"] == recent
    assert state["effective_source"] == "persisted_run"
    assert "completed evaluation" in (state.get("effective_reason") or "")
    assert state["status"] == "OK"


@patch("app.api.data_health._get_effective_orats_timestamp")
@patch("app.api.data_health._load_persisted_state")
def test_fallback_to_live_probe_when_no_persisted_run(mock_load, mock_get_effective):
    """When no completed evaluation run exists, effective_* falls back to live probe."""
    mock_load.return_value = None
    probe_ts = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    mock_get_effective.return_value = (probe_ts, "live_probe", "Using live probe (no completed evaluation run)")

    from app.api.data_health import get_data_health

    state = get_data_health()
    assert state["effective_last_success_at"] == probe_ts
    assert state["effective_source"] == "live_probe"
    assert state["status"] in ("OK", "WARN")
