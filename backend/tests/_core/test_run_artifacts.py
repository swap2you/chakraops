# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Core tests for run artifacts: rotation, purge, runner output, scheduler (Phase 3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.eval.evaluation_store import EvaluationRunFull
from app.core.eval.run_artifacts import (
    PURGE_KEEP_DAYS,
    RECENT_RUNS_COUNT,
    _artifacts_runs_root,
    _get_run_dir,
    _run_id_to_date_and_time,
    _run_dir_name,
    build_latest_response_from_artifacts,
    build_universe_from_latest_artifact,
    get_latest_run_dir,
    purge_old_runs,
    update_recent_manifest,
    update_latest_and_recent,
    write_latest_manifest,
    write_run_artifacts,
)


# ---------------------------------------------------------------------------
# Helpers: use tmp path for artifacts in tests
# ---------------------------------------------------------------------------

@pytest.fixture
def artifacts_tmp(tmp_path):
    """Patch run artifacts root to tmp_path for tests."""
    with patch("app.core.eval.run_artifacts._artifacts_runs_root", return_value=tmp_path / "artifacts" / "runs"):
        yield tmp_path / "artifacts" / "runs"


def _make_completed_run(run_id: str = "eval_20260210_143000_abc12345", completed_at: str | None = None) -> EvaluationRunFull:
    completed_at = completed_at or "2026-02-10T14:30:00+00:00"
    return EvaluationRunFull(
        run_id=run_id,
        started_at="2026-02-10T14:29:00+00:00",
        completed_at=completed_at,
        status="COMPLETED",
        duration_seconds=60.0,
        total=5,
        evaluated=5,
        eligible=2,
        shortlisted=2,
        symbols=[
            {"symbol": "AAPL", "price": 150.0, "bid": 149.9, "ask": 150.1, "volume": 1_000_000, "verdict": "ELIGIBLE", "score": 80},
            {"symbol": "SPY", "price": 450.0, "bid": 449.8, "ask": 450.2, "volume": 2_000_000, "verdict": "HOLD", "score": 50},
        ],
        top_candidates=[{"symbol": "AAPL", "score": 80}],
        source="manual",
    )


# ---------------------------------------------------------------------------
# Runner writes expected files and latest manifest
# ---------------------------------------------------------------------------

def test_run_id_to_date_and_time():
    """run_id parses to YYYY-MM-DD and HHMMSS."""
    date_str, time_str = _run_id_to_date_and_time("eval_20260210_143000_abc12345")
    assert date_str == "2026-02-10"
    assert time_str == "143000"


def test_run_id_invalid_raises():
    """Invalid run_id raises ValueError."""
    with pytest.raises(ValueError, match="run_id does not match"):
        _run_id_to_date_and_time("invalid")
    with pytest.raises(ValueError, match="run_id does not match"):
        _run_id_to_date_and_time("eval_20260210_14300_short")  # 5 digits for time


def test_run_dir_name():
    """Run folder name is run_YYYYMMDD_HHMMSSZ."""
    assert _run_dir_name("eval_20260210_143000_abc12345") == "run_20260210_143000Z"


def test_runner_writes_expected_files_and_latest_manifest(artifacts_tmp):
    """Runner writes snapshot.json, evaluation.json, summary.md and latest manifest."""
    run = _make_completed_run()
    run_dir = write_run_artifacts(run)
    assert run_dir is not None
    assert (run_dir / "snapshot.json").exists()
    assert (run_dir / "evaluation.json").exists()
    assert (run_dir / "summary.md").exists()

    with open(run_dir / "snapshot.json", encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["run_id"] == run.run_id
    assert "symbols" in snap
    assert "AAPL" in snap["symbols"]
    assert snap["symbols"]["AAPL"]["price"] == 150.0

    with open(run_dir / "evaluation.json", encoding="utf-8") as f:
        ev = json.load(f)
    assert ev["run_id"] == run.run_id
    assert ev["status"] == "COMPLETED"
    assert len(ev["symbols"]) == 2

    summary_md = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert run.run_id in summary_md
    assert "COMPLETED" in summary_md

    update_latest_and_recent(run, run_dir)
    latest_path = artifacts_tmp / "latest.json"
    assert latest_path.exists()
    with open(latest_path, encoding="utf-8") as f:
        latest = json.load(f)
    assert latest["run_id"] == run.run_id
    assert latest["path"] == str(run_dir)
    assert latest["completed_at"]


def test_build_universe_from_latest_artifact_returns_shape(artifacts_tmp, tmp_path):
    """build_universe_from_latest_artifact returns symbols + updated_at + as_of + run_id when universe_*.json exists."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    universe_data = {
        "symbols": [
            {"symbol": "AAPL", "last_price": 150.0, "quote_as_of": "2026-02-10T20:00:00Z", "field_sources": {"price": "delayed"}},
            {"symbol": "SPY", "last_price": 450.0},
        ],
        "excluded": [],
        "updated_at": "2026-02-10T14:30:00+00:00",
        "as_of": "2026-02-10T14:30:00+00:00",
        "run_id": "eval_20260210_143000_abc12345",
    }
    (out_dir / "universe_latest.json").write_text(json.dumps(universe_data), encoding="utf-8")

    with patch("app.core.eval.run_artifacts._universe_artifact_dir", return_value=out_dir):
        out = build_universe_from_latest_artifact()

    assert out is not None
    assert out["run_id"] == "eval_20260210_143000_abc12345"
    assert out["updated_at"] == "2026-02-10T14:30:00+00:00"
    assert out["as_of"] == "2026-02-10T14:30:00+00:00"
    assert "symbols" in out
    assert len(out["symbols"]) == 2
    aapl = next(s for s in out["symbols"] if s["symbol"] == "AAPL")
    assert aapl["last_price"] == 150.0
    assert aapl["quote_as_of"] == "2026-02-10T20:00:00Z"
    assert aapl["field_sources"] == {"price": "delayed"}
    assert out.get("excluded") == []
    assert out["all_failed"] is False


def test_build_universe_from_latest_artifact_returns_none_when_no_artifact(tmp_path):
    """build_universe_from_latest_artifact returns None when no universe_*.json exists."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    # out/ exists but has no universe_*.json
    with patch("app.core.eval.run_artifacts._universe_artifact_dir", return_value=out_dir):
        assert build_universe_from_latest_artifact() is None

    # out/ has decision_*.json but NOT universe_* - must still return None
    (out_dir / "decision_latest.json").write_text(json.dumps({"decision_snapshot": {}}), encoding="utf-8")
    with patch("app.core.eval.run_artifacts._universe_artifact_dir", return_value=out_dir):
        assert build_universe_from_latest_artifact() is None


def test_runner_skips_non_completed(artifacts_tmp):
    """write_run_artifacts does nothing for RUNNING or FAILED."""
    run = _make_completed_run()
    run.status = "RUNNING"
    run.completed_at = None
    assert write_run_artifacts(run) is None
    run.status = "FAILED"
    run.completed_at = "2026-02-10T14:30:00+00:00"
    assert write_run_artifacts(run) is None


def test_eod_chain_artifacts_written_when_contract_data_eod(artifacts_tmp):
    """When a symbol has contract_data.source EOD_SNAPSHOT and available, chains/SYMBOL_chain_YYYYMMDD_1600ET.json is written."""
    run = _make_completed_run()
    run.symbols[0]["contract_data"] = {
        "available": True,
        "as_of": "2026-02-10T21:00:00+00:00",
        "source": "EOD_SNAPSHOT",
        "expiration_count": 3,
        "contract_count": 150,
        "required_fields_present": True,
    }
    run_dir = write_run_artifacts(run)
    assert run_dir is not None
    chains_dir = run_dir / "chains"
    assert chains_dir.exists()
    # run_id eval_20260210_143000_abc12345 -> date 20260210
    chain_file = chains_dir / "AAPL_chain_20260210_1600ET.json"
    assert chain_file.exists()
    with open(chain_file, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["symbol"] == "AAPL"
    assert meta["source"] == "EOD_SNAPSHOT"
    assert meta["expiration_count"] == 3
    assert meta["contract_count"] == 150
    assert meta["required_fields_present"] is True
    assert meta["as_of"] == "2026-02-10T21:00:00+00:00"


# ---------------------------------------------------------------------------
# Artifact rotation keeps last 3 runs
# ---------------------------------------------------------------------------

def test_recent_manifest_keeps_last_three(artifacts_tmp):
    """recent.json keeps at most RECENT_RUNS_COUNT (3) entries."""
    root = artifacts_tmp
    root.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        run_id = f"eval_20260210_14000{i}_abc12345"
        path = root / "2026-02-10" / f"run_20260210_14000{i}Z"
        path.mkdir(parents=True, exist_ok=True)
        update_recent_manifest(run_id, path, f"2026-02-10T14:00:0{i}+00:00")

    recent_path = root / "recent.json"
    assert recent_path.exists()
    with open(recent_path, encoding="utf-8") as f:
        recent = json.load(f)
    assert len(recent) == RECENT_RUNS_COUNT
    assert recent[0]["run_id"] == "eval_20260210_140004_abc12345"


# ---------------------------------------------------------------------------
# Purge deletes runs older than 10 days
# ---------------------------------------------------------------------------

def test_purge_removes_runs_older_than_keep_days(artifacts_tmp):
    """purge_old_runs deletes run dirs older than PURGE_KEEP_DAYS."""
    root = artifacts_tmp
    root.mkdir(parents=True, exist_ok=True)
    old_date = (datetime.now(timezone.utc) - timedelta(days=PURGE_KEEP_DAYS + 1)).strftime("%Y-%m-%d")
    old_dir = root / old_date / "run_20260101_120000Z"
    old_dir.mkdir(parents=True, exist_ok=True)
    (old_dir / "evaluation.json").write_text("{}", encoding="utf-8")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_dir = root / today / "run_20260210_120000Z"
    today_dir.mkdir(parents=True, exist_ok=True)
    (today_dir / "evaluation.json").write_text("{}", encoding="utf-8")

    removed = purge_old_runs(keep_days=PURGE_KEEP_DAYS)
    assert removed >= 1
    assert not old_dir.exists()
    assert today_dir.exists()


# ---------------------------------------------------------------------------
# Scheduler does not run outside market hours (mock market calendar)
# ---------------------------------------------------------------------------

def test_scheduler_does_not_run_when_market_closed():
    """Market phase CLOSED/PRE/POST means scheduler must not run evaluation (contract via market_hours)."""
    from app.market.market_hours import get_market_phase, is_market_open

    # Weekend: CLOSED
    try:
        from zoneinfo import ZoneInfo
        utc = ZoneInfo("UTC")
    except ImportError:
        import pytz
        utc = pytz.UTC
    # Saturday 12:00 ET -> 17:00 UTC (winter); use a known Saturday
    sat_noon_et = datetime(2026, 2, 7, 17, 0, 0, tzinfo=utc)  # Sat Feb 7 2026 12:00 ET
    assert get_market_phase(sat_noon_et) == "CLOSED"
    assert is_market_open(sat_noon_et) is False

    # Weekday before 9:30 ET: PRE
    wed_pre = datetime(2026, 2, 10, 14, 0, 0, tzinfo=utc)  # Wed 9:00 ET
    assert get_market_phase(wed_pre) == "PRE"
    assert is_market_open(wed_pre) is False

    # Weekday after 16:00 ET: POST
    wed_post = datetime(2026, 2, 10, 21, 30, 0, tzinfo=utc)  # Wed 16:30 ET
    assert get_market_phase(wed_post) == "POST"
    assert is_market_open(wed_post) is False


# ---------------------------------------------------------------------------
# build_latest_response_from_artifacts
# ---------------------------------------------------------------------------

def test_build_latest_response_from_artifacts_returns_none_when_no_artifacts(artifacts_tmp):
    """When no latest run dir exists, returns None."""
    assert build_latest_response_from_artifacts() is None


def test_build_latest_response_from_artifacts_returns_data_when_present(artifacts_tmp):
    """When latest run dir has evaluation.json, returns same shape as store."""
    run = _make_completed_run()
    run_dir = write_run_artifacts(run)
    assert run_dir is not None
    write_latest_manifest(run.run_id, run_dir, run.completed_at or "")

    resp = build_latest_response_from_artifacts()
    assert resp is not None
    assert resp["has_completed_run"] is True
    assert resp["run_id"] == run.run_id
    assert resp["read_source"] == "artifacts"
    assert resp["counts"]["evaluated"] == 5
    assert len(resp["symbols"]) == 2
