# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Final Closure Batch B — ORATS provider clock, sanity honesty, notifications."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def test_orats_status_uses_provider_not_eval_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.data_health as dh

    recent_eval = datetime.now(timezone.utc).isoformat()
    stale_provider = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

    class _Ptr:
        completed_at = recent_eval

    monkeypatch.setattr(dh, "_LAST_SUCCESS_AT", stale_provider)
    monkeypatch.setattr(dh, "_LAST_ERROR_AT", None)
    monkeypatch.setattr(dh, "_LAST_ERROR_REASON", None)
    monkeypatch.setattr(
        "app.core.eval.evaluation_store.load_latest_pointer",
        lambda: _Ptr(),
    )
    monkeypatch.setattr(dh, "_load_persisted_state", lambda: None)
    state = dh.get_data_health()
    assert state["status"] in ("WARN", "ERROR")
    assert state["effective_source"] == "live_probe"
    assert state["last_success_at"] == stale_provider
    assert state["evaluation_completed_at"] == recent_eval
    # Must not green from eval clock
    assert state["status"] != "OK"


def test_get_data_health_unknown_does_not_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.data_health as dh

    monkeypatch.setattr(dh, "_LAST_SUCCESS_AT", None)
    monkeypatch.setattr(dh, "_LAST_ERROR_AT", None)
    monkeypatch.setattr(dh, "_load_persisted_state", lambda: None)
    called = {"n": 0}

    def _boom():
        called["n"] += 1
        raise AssertionError("must not probe on GET")

    monkeypatch.setattr(dh, "_attempt_live_summary", _boom)
    state = dh.get_data_health()
    assert called["n"] == 0
    assert state["status"] == "UNKNOWN"


def test_notification_occurrence_persists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import notifications_store as ns

    path = tmp_path / "notifications.jsonl"
    monkeypatch.setattr(ns, "_notifications_path", lambda: path)
    ns.append_notification("WARN", "ORATS_WARN", "stale provider", details={"occurrence_count": 1})
    ns.append_notification("WARN", "ORATS_WARN", "stale provider", details={"occurrence_count": 1})
    rows = ns.load_notifications(limit=10, type_filter="ORATS_WARN")
    assert len(rows) == 1
    assert int((rows[0].get("details") or {}).get("occurrence_count") or 0) >= 2
    raw = path.read_text(encoding="utf-8")
    assert '"event": "occurrence"' in raw or '"event":"occurrence"' in raw


def test_positions_sanity_does_not_write_diag_test(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.diagnostics import _run_positions_check

    class _P:
        status = "OPEN"
        symbol = "NVDA"
        position_id = "x"

    monkeypatch.setattr(
        "app.core.positions.service.list_positions",
        lambda **_kw: [_P()],
    )
    # If add_paper_position were called, fail
    monkeypatch.setattr(
        "app.core.positions.service.add_paper_position",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no write")),
        raising=False,
    )
    out = _run_positions_check()
    assert out["status"] == "PASS"
    assert out["details"].get("wrote_test_position") is False


def test_scheduler_skip_not_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.diagnostics import _run_scheduler_check

    monkeypatch.setattr(
        "app.api.server.get_scheduler_status",
        lambda: {"next_run_at": None, "last_run_at": None, "interval_minutes": 30},
    )
    monkeypatch.setattr("app.api.server.get_app_start_time_utc", lambda: None)
    monkeypatch.setattr("app.market.market_hours.is_market_open", lambda: False)
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "CLOSED")
    out = _run_scheduler_check()
    assert out["status"] == "SKIP"
