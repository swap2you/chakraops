# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-ABCD Batch B — market gate + stale RUNNING abandon."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_coordinator_refuses_when_market_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.core.eval import eval_coordinator as coord
    from app.core.eval import evaluation_store as store

    eval_dir = tmp_path / "evaluations"
    eval_dir.mkdir()
    monkeypatch.setattr(store, "_get_evaluations_dir", lambda: eval_dir)
    monkeypatch.setattr(store, "_ensure_evaluations_dir", lambda: eval_dir)
    monkeypatch.setattr(store, "_run_lock_path", lambda: tmp_path / "run.lock")
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "POST")

    with patch("app.core.eval.evaluation_service_v2.evaluate_universe") as mock_eval:
        out = coord.run_universe_evaluation_exclusive(["SPY"], mode="LIVE", trigger="ops_evaluate")
    assert out["started"] is False
    assert out["reason"] == "market_closed"
    assert out["market_phase"] == "POST"
    mock_eval.assert_not_called()
    assert list(eval_dir.glob("eval_*.json")) == []


def test_coordinator_force_allows_when_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.core.eval import eval_coordinator as coord
    from app.core.eval import evaluation_store as store

    eval_dir = tmp_path / "evaluations"
    eval_dir.mkdir()
    monkeypatch.setattr(store, "_get_evaluations_dir", lambda: eval_dir)
    monkeypatch.setattr(store, "_ensure_evaluations_dir", lambda: eval_dir)
    monkeypatch.setattr(store, "_run_lock_path", lambda: tmp_path / "run.lock")
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "POST")

    fake = MagicMock()
    fake.metadata = {
        "pipeline_timestamp": "2026-08-11T00:00:00Z",
        "universe_size": 1,
        "evaluated_count_stage1": 1,
        "evaluated_count_stage2": 0,
        "eligible_count": 0,
    }
    with patch("app.core.eval.evaluation_service_v2.evaluate_universe", return_value=fake):
        out = coord.run_universe_evaluation_exclusive(
            ["SPY"], mode="LIVE", trigger="admin_force", allow_when_closed=True
        )
    assert out["started"] is True


def test_abandon_stale_running_preserves_fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.core.eval import evaluation_store as store

    eval_dir = tmp_path / "evaluations"
    eval_dir.mkdir()
    monkeypatch.setattr(store, "_get_evaluations_dir", lambda: eval_dir)
    monkeypatch.setattr(store, "_ensure_evaluations_dir", lambda: eval_dir)
    monkeypatch.setattr(store, "get_current_run_status", lambda: None)

    old = datetime.now(timezone.utc) - timedelta(hours=3)
    fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
    for rid, started in (("eval_old", old), ("eval_fresh", fresh)):
        payload = {
            "run_id": rid,
            "started_at": started.isoformat(),
            "status": "RUNNING",
            "symbols": [],
            "source": "scheduled",
            "duration_seconds": 0,
            "total": 0,
            "evaluated": 0,
            "eligible": 0,
            "shortlisted": 0,
        }
        (eval_dir / f"{rid}.json").write_text(json.dumps(payload), encoding="utf-8")

    out = store.abandon_stale_running_runs(max_age_sec=3600)
    assert "eval_old" in out["abandoned"]
    assert "eval_fresh" not in out["abandoned"]
    old_data = json.loads((eval_dir / "eval_old.json").read_text(encoding="utf-8"))
    assert old_data["status"] == "ABANDONED"
    assert old_data["error_summary"] == "STALE_RUN_TIMEOUT"
    assert old_data["source"] == "scheduled"
    fresh_data = json.loads((eval_dir / "eval_fresh.json").read_text(encoding="utf-8"))
    assert fresh_data["status"] == "RUNNING"
