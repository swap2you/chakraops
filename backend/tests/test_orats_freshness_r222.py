# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.2: ORATS freshness state (OK / DELAYED / WARN / ERROR)."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Repository-root unittest loads this file without the backend cwd on sys.path.
# The root loader execs this source with its own __file__, so this insert runs
# only when this module is the backend suite.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if _BACKEND_ROOT.name == "backend" and str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


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


def test_get_orats_freshness_state_unknown_when_no_timestamp_and_no_error():
    """Missing provider timestamp with no recorded failure is UNKNOWN, not ERROR.

    System Diagnostics shows this label on the ORATS card. A live strikes HTTP 200
    is not an API failure, and sticky connectivity for the same inputs is UNKNOWN.
    """
    from app.api.data_health import get_orats_freshness_state
    with patch("app.api.data_health._get_effective_orats_timestamp", return_value=(None, "test", "test")):
        with patch("app.api.data_health._LAST_ERROR_AT", None):
            with patch("app.api.data_health._LAST_ERROR_REASON", None):
                state = get_orats_freshness_state()
    assert state.get("state") == "UNKNOWN"
    assert state.get("state_label") == "UNKNOWN"
    assert state.get("threshold_triggered") is None
    assert state.get("as_of") is None


def test_malformed_orats_timestamp_is_unknown():
    from app.api.data_health import get_orats_freshness_state
    with patch("app.api.data_health._get_effective_orats_timestamp", return_value=("not-a-timestamp", "test", "test")):
        with patch("app.api.data_health._LAST_ERROR_AT", None):
            state = get_orats_freshness_state()
    assert state.get("state") == "UNKNOWN"
    assert state.get("threshold_triggered") is None
    assert "malformed" in (state.get("reason") or "").lower()


def test_future_orats_timestamp_is_unknown():
    from app.api.data_health import get_orats_freshness_state
    with patch(
        "app.api.data_health._get_effective_orats_timestamp",
        return_value=("2999-01-01T00:00:00+00:00", "test", "test"),
    ):
        with patch("app.api.data_health._LAST_ERROR_AT", None):
            state = get_orats_freshness_state()
    assert state.get("state") == "UNKNOWN"
    assert state.get("threshold_triggered") is None
    assert "future" in (state.get("reason") or "").lower()


def test_timezone_less_orats_timestamp_is_unknown():
    from app.api.data_health import get_orats_freshness_state
    with patch("app.api.data_health._get_effective_orats_timestamp", return_value=("2026-06-01T12:00:00", "test", "test")):
        with patch("app.api.data_health._LAST_ERROR_AT", None):
            state = get_orats_freshness_state()
    assert state.get("state") == "UNKNOWN"
    assert state.get("threshold_triggered") is None
    assert "timezone" in (state.get("reason") or "").lower()


def test_provider_connectivity_matches_unknown_freshness(monkeypatch):
    """Malformed, future, and timezone-less clocks stay UNKNOWN on both paths."""
    from app.api import data_health as dh

    cases = (
        ("not-a-timestamp", "malformed"),
        ("2999-01-01T00:00:00+00:00", "future"),
        ("2026-06-01T12:00:00", "timezone"),
    )
    monkeypatch.setattr(dh, "_load_persisted_state", lambda: None)
    monkeypatch.setattr(dh, "_LAST_ERROR_AT", None)
    monkeypatch.setattr(dh, "_LAST_ERROR_REASON", None)
    for ts, fragment in cases:
        monkeypatch.setattr(dh, "_LAST_SUCCESS_AT", ts)
        fresh = dh.get_orats_freshness_state()
        health = dh.get_data_health()
        assert fresh.get("state") == "UNKNOWN"
        assert fragment in (fresh.get("reason") or "").lower()
        assert health.get("provider_connectivity_status") == "UNKNOWN"
        assert health.get("status") == "UNKNOWN"
        assert dh._compute_sticky_status(ts) == "UNKNOWN"


def test_persisted_state_read_uses_temp_dir_without_creating_it(tmp_path, monkeypatch):
    """Pytest can point sticky state at a temporary directory and still classify."""
    from app.api import data_health as dh
    from app.core.eval import evaluation_store

    state_file = tmp_path / "nested" / "data_health_state.json"
    snapshot = tmp_path / "missing-snapshot"
    monkeypatch.setattr(dh, "_data_health_state_path", lambda: state_file)
    monkeypatch.setattr(evaluation_store, "_get_evaluations_dir", lambda: snapshot / "evaluations")
    monkeypatch.setattr(dh, "_LAST_SUCCESS_AT", None)
    monkeypatch.setattr(dh, "_LAST_ERROR_AT", None)
    dh._load_persisted_state()
    health = dh.get_data_health()
    assert not state_file.exists()
    assert not state_file.parent.exists()
    assert not snapshot.exists()
    assert health.get("status") == "UNKNOWN"
    assert health.get("provider_connectivity_status") == "UNKNOWN"
    fresh = dh.get_orats_freshness_state()
    assert fresh.get("state") == "UNKNOWN"
    assert dh._compute_sticky_status(None) == "UNKNOWN"


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


# `python -m unittest tests.test_orats_freshness_r222` from backend/ only
# discovers TestCase classes. Pytest functions above are invisible to it, so
# that command used to exit 5 with "NO TESTS RAN". This class is the evidence
# for that invocation. The repository-root loader execs this file; __file__
# there is the root module, so this class stays on the backend module only.
if Path(__file__).resolve().parent.parent.name == "backend":

    class OratsFreshnessBackendUnittest(unittest.TestCase):
        """Backend-module evidence. GET health only; no broker order calls."""

        def test_unknown_clocks_and_recorded_error(self):
            from app.api import data_health as dh

            cases = (
                ("not-a-timestamp", "malformed"),
                ("2999-01-01T00:00:00+00:00", "future"),
                ("2026-06-01T12:00:00", "timezone"),
            )
            with (
                patch.object(dh, "_load_persisted_state", lambda: None),
                patch.object(dh, "_LAST_ERROR_AT", None),
                patch.object(dh, "_LAST_ERROR_REASON", None),
            ):
                for ts, fragment in cases:
                    with patch.object(dh, "_LAST_SUCCESS_AT", ts):
                        fresh = dh.get_orats_freshness_state()
                        health = dh.get_data_health()
                        self.assertEqual(fresh.get("state"), "UNKNOWN")
                        self.assertIsNone(fresh.get("threshold_triggered"))
                        self.assertIn(fragment, (fresh.get("reason") or "").lower())
                        self.assertEqual(health.get("provider_connectivity_status"), "UNKNOWN")
                        self.assertEqual(health.get("status"), "UNKNOWN")
                        self.assertEqual(dh._compute_sticky_status(ts), "UNKNOWN")
                with (
                    patch.object(dh, "_LAST_SUCCESS_AT", None),
                    patch.object(dh, "_LAST_ERROR_AT", "2026-01-01T12:00:00+00:00"),
                    patch.object(dh, "_LAST_ERROR_REASON", "recorded provider failure"),
                ):
                    failed = dh.get_orats_freshness_state()
                    self.assertEqual(failed.get("state"), "ERROR")
                    self.assertEqual(failed.get("threshold_triggered"), "error")

        def test_missing_state_does_not_create_directories(self):
            import tempfile

            from app.api import data_health as dh
            from app.core.eval import evaluation_store

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                state_file = tmp_path / "nested" / "data_health_state.json"
                snapshot = tmp_path / "missing-snapshot"
                with (
                    patch.object(dh, "_data_health_state_path", lambda: state_file),
                    patch.object(evaluation_store, "_get_evaluations_dir", lambda: snapshot / "evaluations"),
                    patch.object(dh, "_LAST_SUCCESS_AT", None),
                    patch.object(dh, "_LAST_ERROR_AT", None),
                ):
                    dh._load_persisted_state()
                    health = dh.get_data_health()
                    self.assertFalse(state_file.exists())
                    self.assertFalse(state_file.parent.exists())
                    self.assertFalse(snapshot.exists())
                    self.assertEqual(health.get("status"), "UNKNOWN")
                    self.assertEqual(health.get("provider_connectivity_status"), "UNKNOWN")

        def test_loopback_health_get_only(self):
            from fastapi.testclient import TestClient
            from app.api.server import app

            client = TestClient(app)
            health = client.get("/health")
            healthz = client.get("/api/healthz")
            self.assertEqual(health.status_code, 200)
            self.assertIs(health.json().get("ok"), True)
            self.assertEqual(health.json().get("status"), "healthy")
            self.assertEqual(healthz.status_code, 200)
            self.assertIs(healthz.json().get("ok"), True)
            self.assertEqual(healthz.json().get("status"), "ok")
