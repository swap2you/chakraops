# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.2: Shares targets/stops lifecycle, exit signal (request-time only), notification dedupe, no FAIL/WARN in UI."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.next_action_r241 import compute_shares_exit_signal


def test_compute_shares_exit_signal_target_hit():
    """R25.2: When last_price >= target_price, hit_type TARGET, reason_safe 'Target hit'."""
    hit_type, reason = compute_shares_exit_signal(last_price=152.0, target_price=150.0, stop_price=140.0)
    assert hit_type == "TARGET"
    assert reason == "Target hit"
    assert "FAIL" not in reason and "WARN" not in reason


def test_compute_shares_exit_signal_stop_hit():
    """R25.2: When last_price <= stop_price, hit_type STOP, reason_safe 'Stop hit'."""
    hit_type, reason = compute_shares_exit_signal(last_price=138.0, target_price=150.0, stop_price=140.0)
    assert hit_type == "STOP"
    assert reason == "Stop hit"
    assert "FAIL" not in reason and "WARN" not in reason


def test_compute_shares_exit_signal_no_hit():
    """R25.2: When price between stop and target, no hit."""
    hit_type, reason = compute_shares_exit_signal(last_price=145.0, target_price=150.0, stop_price=140.0)
    assert hit_type is None
    assert reason == ""


def test_compute_shares_exit_signal_no_last_price():
    """R25.2: When last_price is None, no hit."""
    hit_type, reason = compute_shares_exit_signal(last_price=None, target_price=150.0, stop_price=140.0)
    assert hit_type is None
    assert reason == ""


def test_shares_exit_fields_not_in_persisted_artifact():
    """R25.2: Persisted decision artifact must not contain shares_exit_* (request-time only)."""
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2

    artifact = DecisionArtifactV2(
        metadata={"artifact_version": 2, "run_id": "test"},
        symbols=[],
        selected_candidates=[],
    )
    data = artifact.to_dict_persist()
    json_str = json.dumps(data, default=str)
    assert "shares_exit_hit_type" not in json_str
    assert "shares_exit_reason_safe" not in json_str
    assert "shares_exit_last_price" not in json_str
    assert "shares_exit_target_price" not in json_str
    assert "shares_exit_stop_price" not in json_str
    assert "shares_exit_as_of_ts" not in json_str


def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _all_strings(x)


def test_symbol_diagnostics_response_no_fail_warn():
    """R25.2: GET symbol-diagnostics response must not contain FAIL_ or WARN_ in JSON."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/symbol-diagnostics", params={"symbol": "SPY"})
    if r.status_code != 200:
        pytest.skip("symbol-diagnostics may 404 if no store; skip")
    data = r.json()
    for s in _all_strings(data):
        assert "FAIL_" not in s
        assert "WARN_" not in s


def test_action_needed_response_no_fail_warn_r252():
    """R25.2: GET action-needed response must not contain FAIL_ or WARN_ (reconfirm)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/action-needed")
    assert r.status_code == 200
    data = r.json()
    for s in _all_strings(data):
        assert "FAIL_" not in s
        assert "WARN_" not in s


def test_maybe_append_shares_exit_notification_dedupe():
    """R25.2: Second call for same symbol+hit_type within window does not append duplicate."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import (
                    load_notifications,
                    maybe_append_shares_exit_notification,
                )
                # Use unique symbol so we don't match any existing notification
                symbol = "R252_DEDUPE_TEST"
                ok1 = maybe_append_shares_exit_notification(
                    symbol=symbol, hit_type="TARGET", last_price=155.0,
                    target_price=150.0, stop_price=140.0, as_of_ts="2026-01-01T12:00:00Z",
                )
                assert ok1 is True
                ok2 = maybe_append_shares_exit_notification(
                    symbol=symbol, hit_type="TARGET", last_price=155.0,
                    target_price=150.0, stop_price=140.0, as_of_ts="2026-01-01T12:00:00Z",
                )
                assert ok2 is False
                recs = [r for r in load_notifications(limit=50) if r.get("type") == "SHARES_EXIT_SIGNAL" and r.get("symbol") == symbol]
                assert len(recs) == 1
