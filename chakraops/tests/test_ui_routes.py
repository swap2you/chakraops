# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for /api/ui/* endpoints: LIVE vs MOCK, traversal protection, API key."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


def _get_app():
    from app.api.server import app
    return app


def test_ui_decision_files_live_excludes_mock(tmp_path):
    """LIVE mode excludes decision_MOCK.json and out/mock."""
    from fastapi.testclient import TestClient
    (tmp_path / "decision_2026.json").write_text('{"ok": true}')
    (tmp_path / "decision_MOCK.json").write_text('{"mock": true}')
    (tmp_path / "decision_latest.json").write_text('{"latest": true}')
    app = _get_app()
    with patch("app.api.ui_routes._output_dir", return_value=tmp_path):
        client = TestClient(app)
        r = client.get("/api/ui/decision/files?mode=LIVE")
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "LIVE"
    names = [f["name"] for f in data["files"]]
    assert "decision_MOCK.json" not in names
    assert "decision_latest.json" in names
    assert "decision_2026.json" in names


def test_ui_decision_files_mock_reads_mock_dir(tmp_path):
    """MOCK mode reads from out/mock only."""
    from fastapi.testclient import TestClient
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "scenario_1.json").write_text('{"scenario": true}')
    (tmp_path / "decision_latest.json").write_text('{"live": true}')
    app = _get_app()
    with patch("app.api.ui_routes._output_dir", return_value=tmp_path):
        client = TestClient(app)
        r = client.get("/api/ui/decision/files?mode=MOCK")
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "MOCK"
    assert "mock" in data["dir"].lower() or "mock" in data["dir"]
    names = [f["name"] for f in data["files"]]
    assert "scenario_1.json" in names


def test_ui_decision_file_traversal_blocked(tmp_path):
    """File traversal (.. or /) in filename returns 400."""
    from fastapi.testclient import TestClient
    (tmp_path / "decision_latest.json").write_text('{"ok": true}')
    app = _get_app()
    with patch("app.api.ui_routes._output_dir", return_value=tmp_path):
        client = TestClient(app)
        for bad in ["../../../etc/passwd", "..\\..\\etc\\passwd", "a/b", "a\\b"]:
            r = client.get(f"/api/ui/decision/file/{bad}?mode=LIVE")
            assert r.status_code in (400, 404), f"Expected 400/404 for {bad}"


def test_ui_decision_file_only_allowed_filenames(tmp_path):
    """Can only fetch filenames returned by /files."""
    from fastapi.testclient import TestClient
    (tmp_path / "decision_latest.json").write_text('{"ok": true}')
    app = _get_app()
    with patch("app.api.ui_routes._output_dir", return_value=tmp_path):
        client = TestClient(app)
        r = client.get("/api/ui/decision/file/decision_other.json?mode=LIVE")
    assert r.status_code == 404


def test_ui_decision_files_ordering(tmp_path):
    """Files are sorted newest-first by mtime."""
    from fastapi.testclient import TestClient
    import time
    (tmp_path / "decision_a.json").write_text("{}")
    time.sleep(0.01)
    (tmp_path / "decision_b.json").write_text("{}")
    time.sleep(0.01)
    (tmp_path / "decision_c.json").write_text("{}")
    app = _get_app()
    with patch("app.api.ui_routes._output_dir", return_value=tmp_path):
        client = TestClient(app)
        r = client.get("/api/ui/decision/files?mode=LIVE")
    assert r.status_code == 200
    names = [f["name"] for f in r.json()["files"]]
    assert names[0] == "decision_c.json"
    assert names[-1] == "decision_a.json"


def test_ui_decision_latest_rejects_mock_data_source():
    """LIVE mode returns 400 when artifact has data_source mock/scenario."""
    from fastapi.testclient import TestClient
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary

    sym = SymbolEvalSummary(
        symbol="SPY",
        verdict="HOLD",
        final_verdict="HOLD",
        score=50,
        band="C",
        primary_reason="test",
        stage_status="RUN",
        stage1_status="PASS",
        stage2_status="NOT_RUN",
        provider_status="OK",
        data_freshness=None,
        evaluated_at=None,
        strategy=None,
        price=None,
        expiration=None,
        has_candidates=False,
        candidate_count=0,
    )
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "data_source": "mock"},
        symbols=[sym],
        selected_candidates=[],
    )
    class MockStore:
        def get_latest(self):
            return artifact
        def reload_from_disk(self):
            pass
    mock_store = MockStore()

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2", return_value=mock_store):
        client = TestClient(app)
        r = client.get("/api/ui/decision/latest?mode=LIVE")
    assert r.status_code == 400


def test_ui_positions_post_persists_and_get_returns(tmp_path):
    """POST /api/ui/positions creates a paper position; GET /api/ui/positions returns it. Skip if fastapi missing."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    def _fake_positions_dir():
        return positions_dir

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", side_effect=_fake_positions_dir):
        client = TestClient(app)
        get0 = client.get("/api/ui/positions")
        assert get0.status_code == 200
        assert get0.json().get("positions") == []

        post = client.post(
            "/api/ui/positions",
            json={
                "symbol": "SPY",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 450.0,
                "expiration": "2026-03-21",
                "credit_expected": 2.50,
            },
        )
        assert post.status_code == 200
        body = post.json()
        assert body.get("symbol") == "SPY"
        assert body.get("strategy") == "CSP"
        assert body.get("position_id")

        get1 = client.get("/api/ui/positions")
        assert get1.status_code == 200
        positions = get1.json().get("positions") or []
        assert len(positions) == 1
        assert positions[0].get("symbol") == "SPY"
        assert positions[0].get("status") == "OPEN"


def test_ui_diagnostics_run_and_history(tmp_path):
    """POST /api/ui/diagnostics/run runs checks; GET /api/ui/diagnostics/history returns runs. Skip if fastapi missing."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _fake_diagnostics_path():
        return out_dir / "diagnostics_history.jsonl"

    app = _get_app()
    with patch("app.api.diagnostics._diagnostics_history_path", side_effect=_fake_diagnostics_path):
        with patch("app.core.positions.store._get_positions_dir", return_value=tmp_path / "positions"):
            (tmp_path / "positions").mkdir(parents=True, exist_ok=True)
            client = TestClient(app)

            hist0 = client.get("/api/ui/diagnostics/history?limit=5")
            assert hist0.status_code == 200
            assert hist0.json().get("runs") == []

            run = client.post("/api/ui/diagnostics/run")
            assert run.status_code == 200
            body = run.json()
            assert "timestamp_utc" in body
            assert "checks" in body
            assert "overall_status" in body
            assert body["overall_status"] in ("PASS", "WARN", "FAIL")
            assert len(body["checks"]) >= 1

            hist1 = client.get("/api/ui/diagnostics/history?limit=5")
            assert hist1.status_code == 200
            runs = hist1.json().get("runs") or []
            assert len(runs) >= 1
            assert runs[0]["timestamp_utc"] == body["timestamp_utc"]


def test_ui_decision_latest_includes_evaluation_timestamp(tmp_path):
    """Phase 9: decision/latest includes evaluation_timestamp_utc and decision_store_mtime_utc."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary

    pipeline_ts = "2026-02-17T20:58:29Z"
    sym = SymbolEvalSummary(
        symbol="SPY",
        verdict="HOLD",
        final_verdict="HOLD",
        score=50,
        band="C",
        primary_reason="test",
        stage_status="RUN",
        stage1_status="PASS",
        stage2_status="NOT_RUN",
        provider_status="OK",
        data_freshness=None,
        evaluated_at=None,
        strategy=None,
        price=None,
        expiration=None,
        has_candidates=False,
        candidate_count=0,
    )
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "pipeline_timestamp": pipeline_ts},
        symbols=[sym],
        selected_candidates=[],
    )

    class MockStore:
        def get_latest(self):
            return artifact
        def reload_from_disk(self):
            pass

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2", return_value=MockStore()):
        with patch("app.api.ui_routes._get_decision_store_mtime_utc", return_value="2026-02-17T20:59:00Z"):
            client = TestClient(app)
            r = client.get("/api/ui/decision/latest?mode=LIVE")
    assert r.status_code == 200
    data = r.json()
    assert "evaluation_timestamp_utc" in data
    assert data["evaluation_timestamp_utc"] == pipeline_ts
    assert "decision_store_mtime_utc" in data


def test_ui_market_status_returns_phase():
    """Phase 9: GET /api/ui/market/status returns is_open, phase, now_utc, now_et."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    client = TestClient(app)
    r = client.get("/api/ui/market/status")
    assert r.status_code == 200
    data = r.json()
    assert "is_open" in data
    assert "phase" in data
    assert "now_utc" in data


def test_ui_eval_run_409_when_market_closed():
    """Phase 9: POST eval/run returns 409 when market closed and force=false."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    with patch("app.market.market_hours.get_market_phase", return_value="POST"):
        client = TestClient(app)
        r = client.post("/api/ui/eval/run")
    assert r.status_code == 409
    assert "Market is closed" in r.json().get("detail", "")


def test_ui_eval_run_success_when_force_true():
    """Phase 9: POST eval/run succeeds when market closed but force=true (if eval succeeds)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    with patch("app.market.market_hours.get_market_phase", return_value="POST"):
        with patch("app.api.data_health.get_universe_symbols", return_value=["SPY"]):
            with patch("app.core.eval.evaluation_service_v2.evaluate_universe") as mock_eval:
                mock_artifact = type("A", (), {"metadata": {"pipeline_timestamp": "2026-02-17T21:00:00Z"}})()
                mock_eval.return_value = mock_artifact
                client = TestClient(app)
                r = client.post("/api/ui/eval/run?force=true")
    assert r.status_code == 200


def test_ui_symbol_recompute_409_when_market_closed():
    """Phase 9: POST symbols/{symbol}/recompute returns 409 when market closed and force=false."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    with patch("app.market.market_hours.get_market_phase", return_value="POST"):
        client = TestClient(app)
        r = client.post("/api/ui/symbols/SPY/recompute")
    assert r.status_code == 409
    assert "Market is closed" in r.json().get("detail", "")


def test_ui_snapshots_freeze_archive_only_when_market_closed(tmp_path):
    """PR2: POST snapshots/freeze runs archive_only when market closed (no eval)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    snap_dir = tmp_path / "snapshots" / "2026-02-17_eod"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot_manifest.json").write_text(json.dumps({"created_at_utc": "2026-02-17T21:00:00Z", "files": []}))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    store_path = out_dir / "decision_latest.json"
    store_path.write_text("{}")

    app = _get_app()
    with patch("app.market.market_hours.get_market_phase", return_value="POST"):
        with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
            with patch("app.core.snapshots.freeze.run_freeze_snapshot") as mock_freeze:
                mock_freeze.return_value = {"snapshot_dir": str(snap_dir), "manifest": {}, "copied_files": []}
                client = TestClient(app)
                r = client.post("/api/ui/snapshots/freeze?skip_eval=true")
    assert r.status_code == 200
    data = r.json()
    assert data["mode_used"] == "archive_only"
    assert data["ran_eval"] is False
    mock_freeze.assert_called_once()


def test_ui_snapshots_freeze_eval_then_archive_when_market_open(tmp_path):
    """PR2: POST snapshots/freeze runs eval_then_archive when market OPEN and before 4 PM."""
    pytest.importorskip("fastapi")
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    store_path = out_dir / "decision_latest.json"
    store_path.write_text("{}")
    snap_dir = out_dir / "snapshots" / "2026-02-17_eod"
    snap_dir.mkdir(parents=True)
    # 3:30 PM ET = 20:30 UTC on Feb 17 2026 (EST)
    mock_now = datetime(2026, 2, 17, 20, 30, 0, tzinfo=timezone.utc)

    app = _get_app()
    with patch("app.market.market_hours.get_market_phase", return_value="OPEN"):
        with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
            with patch("app.api.data_health.get_universe_symbols", return_value=["SPY"]):
                with patch("app.core.eval.evaluation_service_v2.evaluate_universe") as mock_eval:
                    with patch("app.core.snapshots.freeze.run_freeze_snapshot") as mock_freeze:
                        with patch("app.api.ui_routes.datetime") as mock_dt:
                            mock_dt.now.return_value = mock_now
                            mock_eval.return_value = type("A", (), {"metadata": {"pipeline_timestamp": "2026-02-17T20:58:00Z"}})()
                            mock_freeze.return_value = {"snapshot_dir": str(snap_dir), "manifest": {}, "copied_files": ["decision_latest.json"]}
                            client = TestClient(app)
                            r = client.post("/api/ui/snapshots/freeze")
    assert r.status_code == 200
    data = r.json()
    assert data["mode_used"] == "eval_then_archive"
    assert data["ran_eval"] is True
    mock_eval.assert_called_once()
    mock_freeze.assert_called_once()


def test_ui_snapshots_latest_returns_manifest(tmp_path):
    """PR2: GET snapshots/latest returns manifest when snapshots exist."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    snap_dir = tmp_path / "snapshots" / "2026-02-17_eod"
    snap_dir.mkdir(parents=True)
    manifest = {"created_at_utc": "2026-02-17T21:00:00Z", "created_at_et": "2026-02-17T16:00:00-05:00", "files": [{"name": "decision_latest.json", "size_bytes": 100}]}
    (snap_dir / "snapshot_manifest.json").write_text(json.dumps(manifest))
    out_dir = tmp_path
    store_path = out_dir / "decision_latest.json"

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        client = TestClient(app)
        r = client.get("/api/ui/snapshots/latest")
    assert r.status_code == 200
    data = r.json()
    assert "snapshot_dir" in data
    assert "manifest" in data
    assert data["manifest"]["created_at_utc"] == "2026-02-17T21:00:00Z"


def test_ui_snapshots_latest_404_when_none(tmp_path):
    """PR2: GET snapshots/latest returns 404 when no snapshots."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "snapshots").mkdir()
    store_path = out_dir / "decision_latest.json"

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        client = TestClient(app)
        r = client.get("/api/ui/snapshots/latest")
    assert r.status_code == 404
