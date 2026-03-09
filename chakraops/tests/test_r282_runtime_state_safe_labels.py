# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.2: UI-facing runtime state files (out/) must not persist raw FAIL/WARN/PASS; safe status + label only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN_TOKEN = re.compile(r"\b(FAIL|WARN|PASS)\b")


def test_mark_refresh_state_writer_output_has_no_forbidden_tokens(tmp_path) -> None:
    """write_mark_refresh_state persists only safe status/status_label; no FAIL/WARN/PASS in file."""
    from app.core.portfolio.mark_refresh_state import write_mark_refresh_state, load_mark_refresh_state, _mark_refresh_state_path
    with patch("app.core.portfolio.mark_refresh_state._mark_refresh_state_path", return_value=tmp_path / "mark_refresh_state.json"):
        write_mark_refresh_state(0, 0, ["error one"])
        path = tmp_path / "mark_refresh_state.json"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        assert "status" in data
        assert "status_label" in data
        assert FORBIDDEN_TOKEN.search(text) is None, "File must not contain literal FAIL, WARN, or PASS"
        assert data.get("status") in ("OK", "Blocked", "Degraded", "Review")
        assert "FAIL" not in text
        assert "WARN" not in text
        assert "PASS" not in text


def test_mark_refresh_state_writer_pass_case(tmp_path) -> None:
    """PASS case -> status OK, no forbidden tokens."""
    from app.core.portfolio.mark_refresh_state import write_mark_refresh_state
    with patch("app.core.portfolio.mark_refresh_state._mark_refresh_state_path", return_value=tmp_path / "mark_refresh_state.json"):
        write_mark_refresh_state(5, 0, [])
        text = (tmp_path / "mark_refresh_state.json").read_text(encoding="utf-8")
        assert FORBIDDEN_TOKEN.search(text) is None
        data = json.loads(text)
        assert data.get("status") == "OK"


def test_portfolio_risk_notify_state_writer_output_has_no_forbidden_tokens(tmp_path) -> None:
    """risk_notify_state _save_state persists only safe status/status_label; no FAIL/WARN in file."""
    from app.core.portfolio.risk_notify_state import _risk_notify_state_path, _save_state, _load_state
    path = tmp_path / "portfolio_risk_notify_state.json"
    with patch("app.core.portfolio.risk_notify_state._risk_notify_state_path", return_value=path):
        _save_state("sig123", "2026-03-01T12:00:00Z", "FAIL")
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert FORBIDDEN_TOKEN.search(text) is None
        data = json.loads(text)
        assert data.get("status") in ("OK", "Blocked", "Degraded", "Review")
        assert "FAIL" not in text
        assert "WARN" not in text
        assert "PASS" not in text


def test_runtime_state_writers_do_not_write_decision_latest(tmp_path) -> None:
    """Mark refresh and risk notify state writers do not write to out/decision_latest.json."""
    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text("{}")
    before = decision_path.read_text()

    with patch("app.core.portfolio.mark_refresh_state._mark_refresh_state_path", return_value=tmp_path / "mark_refresh_state.json"):
        from app.core.portfolio.mark_refresh_state import write_mark_refresh_state
        write_mark_refresh_state(1, 0, [])

    with patch("app.core.portfolio.risk_notify_state._risk_notify_state_path", return_value=tmp_path / "portfolio_risk_notify_state.json"):
        from app.core.portfolio.risk_notify_state import _save_state
        _save_state("s", "2026-03-01T12:00:00Z", "WARN")

    assert decision_path.read_text() == before


def test_load_mark_refresh_state_backward_compat(tmp_path) -> None:
    """load_mark_refresh_state returns safe fields; old file with last_result is normalized."""
    from app.core.portfolio.mark_refresh_state import load_mark_refresh_state
    with patch("app.core.portfolio.mark_refresh_state._mark_refresh_state_path", return_value=tmp_path / "mark_refresh_state.json"):
        path = tmp_path / "mark_refresh_state.json"
        path.write_text(json.dumps({
            "last_run_at_utc": "2026-03-01T12:00:00Z",
            "last_result": "FAIL",
            "updated_count": 0,
            "skipped_count": 0,
            "error_count": 1,
            "errors_sample": ["e1"],
        }))
        state = load_mark_refresh_state()
        assert state is not None
        assert state.get("status") in ("OK", "Blocked", "Degraded", "Review")
        assert state.get("last_result") not in ("FAIL", "WARN", "PASS") or state.get("last_result") == state.get("status")
        assert "FAIL" not in json.dumps(state)


def test_normalize_runtime_status() -> None:
    """normalize_runtime_status maps PASS/FAIL/WARN to safe (status, label)."""
    from app.core.portfolio.runtime_state_safe_labels import normalize_runtime_status, normalize_mark_refresh_result
    assert normalize_runtime_status("PASS") == ("OK", "OK")
    assert normalize_runtime_status("FAIL") == ("Degraded", "Limit breach")
    assert normalize_runtime_status("WARN") == ("Degraded", "Advisory")
    assert normalize_mark_refresh_result("PASS") == ("OK", "OK")
    assert normalize_mark_refresh_result("FAIL") == ("Blocked", "No update")
    assert normalize_mark_refresh_result("WARN") == ("Degraded", "Partial update")
