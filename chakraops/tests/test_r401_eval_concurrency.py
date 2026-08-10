# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40.1: exclusive universe evaluation concurrency."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_second_exclusive_run_returns_already_running(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.eval import eval_coordinator as coord
    from app.core.eval import evaluation_store as store

    # Isolate lock file under tmp
    monkeypatch.setattr(store, "_run_lock_path", lambda: tmp_path / "run.lock")
    monkeypatch.setattr(store, "_ensure_evaluations_dir", lambda: None)
    # Clear any prior lock
    lock = tmp_path / "run.lock"
    if lock.exists():
        lock.unlink()

    fake_artifact = MagicMock()
    fake_artifact.metadata = {
        "pipeline_timestamp": "2026-08-10T00:00:00Z",
        "universe_size": 1,
        "evaluated_count_stage1": 1,
        "evaluated_count_stage2": 0,
        "eligible_count": 0,
    }

    # Hold lock via first begin without end
    ok, run_id = coord.try_begin_universe_evaluation("test_hold")
    assert ok is True
    assert run_id

    with patch(
        "app.core.eval.evaluation_service_v2.evaluate_universe",
        return_value=fake_artifact,
    ) as mock_eval:
        second = coord.run_universe_evaluation_exclusive(["SPY"], mode="LIVE", trigger="test_second")
        assert second.get("started") is False
        assert second.get("reason") == "already_running"
        mock_eval.assert_not_called()

    coord.end_universe_evaluation()

    with patch(
        "app.core.eval.evaluation_service_v2.evaluate_universe",
        return_value=fake_artifact,
    ) as mock_eval:
        third = coord.run_universe_evaluation_exclusive(["SPY"], mode="LIVE", trigger="test_third")
        assert third.get("started") is True
        assert third.get("reason") == "ok"
        mock_eval.assert_called_once()
