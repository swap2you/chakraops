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
