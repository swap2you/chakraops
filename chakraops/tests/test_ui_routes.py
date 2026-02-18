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


def test_ui_positions_post_409_when_collateral_exceeds_max_per_trade(tmp_path):
    """Phase 11.0: POST positions returns 409 when collateral exceeds max_collateral_per_trade."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    accounts_dir = tmp_path / "accounts"
    positions_dir.mkdir(parents=True, exist_ok=True)
    accounts_dir.mkdir(parents=True, exist_ok=True)
    accounts_file = accounts_dir / "accounts.json"
    accounts_file.write_text(
        '[{"account_id":"acct_1","provider":"Manual","account_type":"Taxable","total_capital":100000,'
        '"max_capital_per_trade_pct":5,"max_total_exposure_pct":30,"allowed_strategies":["CSP"],'
        '"is_default":true,"max_collateral_per_trade":30000,"max_total_collateral":100000}]',
        encoding="utf-8",
    )

    def _fake_accounts_path():
        return accounts_file

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        with patch("app.core.accounts.store._accounts_path", side_effect=_fake_accounts_path):
            client = TestClient(app)
            # CSP 1 @ 450 = 45000 collateral > 30000 max
            r = client.post(
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
    assert r.status_code == 409
    assert "exceeds max per trade" in str(r.json().get("detail", {}))


def test_ui_positions_post_success_when_within_limits(tmp_path):
    """Phase 11.0: POST positions succeeds when within sizing limits; decision_ref persisted."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    accounts_dir = tmp_path / "accounts"
    positions_dir.mkdir(parents=True, exist_ok=True)
    accounts_dir.mkdir(parents=True, exist_ok=True)
    accounts_file = accounts_dir / "accounts.json"
    accounts_file.write_text(
        '[{"account_id":"acct_1","provider":"Manual","account_type":"Taxable","total_capital":100000,'
        '"max_capital_per_trade_pct":5,"max_total_exposure_pct":30,"allowed_strategies":["CSP"],'
        '"is_default":true,"max_collateral_per_trade":50000,"max_total_collateral":100000}]',
        encoding="utf-8",
    )

    def _fake_accounts_path():
        return accounts_file

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        with patch("app.core.accounts.store._accounts_path", side_effect=_fake_accounts_path):
            client = TestClient(app)
            r = client.post(
                "/api/ui/positions",
                json={
                    "symbol": "SPY",
                    "strategy": "CSP",
                    "contracts": 1,
                    "strike": 450.0,
                    "expiration": "2026-03-21",
                    "credit_expected": 2.50,
                    "decision_ref": {"evaluation_timestamp_utc": "2026-02-17T20:00:00Z", "artifact_source": "LIVE"},
                },
            )
    assert r.status_code == 200
    body = r.json()
    assert body.get("symbol") == "SPY"
    assert body.get("decision_ref") is not None
    assert body["decision_ref"].get("evaluation_timestamp_utc") == "2026-02-17T20:00:00Z"


def test_ui_position_decision_with_run_id(tmp_path):
    """Phase 11.1/11.2: Create position with decision_ref.run_id; write history; GET decision returns exact_run when history exists."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2

    run_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    sym = SymbolEvalSummary(
        symbol="SPY",
        verdict="ELIGIBLE",
        final_verdict="ELIGIBLE",
        score=75,
        band="B",
        primary_reason="test",
        stage_status="RUN",
        stage1_status="PASS",
        stage2_status="PASS",
        provider_status="OK",
        data_freshness=None,
        evaluated_at=None,
        strategy=None,
        price=None,
        expiration=None,
        has_candidates=True,
        candidate_count=1,
    )
    artifact = DecisionArtifactV2(
        metadata={
            "artifact_version": "v2",
            "pipeline_timestamp": "2026-02-17T21:00:00Z",
            "run_id": run_id,
        },
        symbols=[sym],
        selected_candidates=[],
    )

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    try:
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.set_latest(artifact)  # writes latest + history

        app = _get_app()
        with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
            client = TestClient(app)
            post = client.post(
                "/api/ui/positions",
                json={
                    "symbol": "SPY",
                    "strategy": "CSP",
                    "contracts": 1,
                    "strike": 450.0,
                    "expiration": "2026-03-21",
                    "credit_expected": 2.50,
                    "decision_ref": {"run_id": run_id, "evaluation_timestamp_utc": "2026-02-17T21:00:00Z"},
                },
            )
        assert post.status_code == 200
        pid = post.json()["position_id"]

        with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
            client = TestClient(app)
            r = client.get(f"/api/ui/positions/{pid}/decision")
        assert r.status_code == 200
        data = r.json()
        assert data.get("run_id") == run_id
        assert data.get("exact_run") is True
        assert "warning" not in data or data.get("warning") is None
    finally:
        reset_output_dir()


def test_ui_position_decision_warning_when_run_mismatch(tmp_path):
    """Phase 11.1: Position with run_id but current artifact has different run_id returns warning."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary

    pos_run_id = "old-run-1111-2222-3333-444455556666"
    current_run_id = "new-run-aaaa-bbbb-cccc-ddddeeeeffff"
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
        metadata={
            "artifact_version": "v2",
            "pipeline_timestamp": "2026-02-17T22:00:00Z",
            "run_id": current_run_id,
        },
        symbols=[sym],
        selected_candidates=[],
    )

    class MockStore:
        def get_latest(self):
            return artifact

        def reload_from_disk(self):
            pass

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2", return_value=MockStore()):
            client = TestClient(app)
            post = client.post(
                "/api/ui/positions",
                json={
                    "symbol": "SPY",
                    "strategy": "CSP",
                    "contracts": 1,
                    "strike": 450.0,
                    "expiration": "2026-03-21",
                    "credit_expected": 2.50,
                    "decision_ref": {"run_id": pos_run_id},
                },
            )
    assert post.status_code == 200
    pid = post.json()["position_id"]

    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2", return_value=MockStore()):
            client = TestClient(app)
            r = client.get(f"/api/ui/positions/{pid}/decision")
    assert r.status_code == 200
    data = r.json()
    assert data.get("exact_run") is False
    assert "exact run not available" in (data.get("warning") or "")


def test_ui_positions_close_and_delete_guardrail(tmp_path):
    """Phase 10.0: Close position computes realized_pnl; delete allowed only for CLOSED/test."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        # Create OPEN position: CSP 1 contract @ 450, credit 2.50
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
        pos = post.json()
        pid = pos["position_id"]

        # Try delete while OPEN -> 409
        del_open = client.delete(f"/api/ui/positions/{pid}")
        assert del_open.status_code == 409

        # Close with close_price 1.00 (buy back at $1)
        close_res = client.post(
            f"/api/ui/positions/{pid}/close",
            json={"close_price": 1.00},
        )
        assert close_res.status_code == 200
        closed = close_res.json()
        assert closed.get("status") == "CLOSED"
        assert "realized_pnl" in closed
        # open_credit 2.50 total 250, close_debit 100, pnl = 250 - 100 = 150
        rpnl = closed.get("realized_pnl")
        assert rpnl is not None
        assert abs(rpnl - 150.0) < 0.01

        # Delete CLOSED position -> 200
        del_closed = client.delete(f"/api/ui/positions/{pid}")
        assert del_closed.status_code == 200
        assert del_closed.json().get("deleted") == pid

        # Verify gone
        get_after = client.get("/api/ui/positions")
        assert get_after.status_code == 200
        assert len(get_after.json().get("positions") or []) == 0


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


def test_ui_universe_includes_selected_contract_key_when_eligible(tmp_path):
    """Phase 11.3: Universe row includes selected_contract_key and option_symbol when ELIGIBLE."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2

    artifact = {
        "metadata": {
            "artifact_version": "v2",
            "pipeline_timestamp": "2026-02-17T20:00:00Z",
            "run_id": "run-11-3-test",
        },
        "symbols": [
            {
                "symbol": "SPY",
                "verdict": "ELIGIBLE",
                "final_verdict": "ELIGIBLE",
                "score": 65,
                "band": "B",
                "primary_reason": "test",
                "stage_status": "RUN",
                "stage1_status": "PASS",
                "stage2_status": "PASS",
                "provider_status": "OK",
                "data_freshness": "2026-02-17",
                "evaluated_at": "2026-02-17",
                "strategy": "CSP",
                "price": 450.0,
                "expiration": "2026-03-20",
                "has_candidates": True,
                "candidate_count": 1,
            }
        ],
        "selected_candidates": [
            {
                "symbol": "SPY",
                "strategy": "CSP",
                "expiry": "2026-03-20",
                "strike": 450.0,
                "delta": -0.25,
                "credit_estimate": 2.50,
                "max_loss": 45000,
                "why_this_trade": "test",
                "contract_key": "450-2026-03-20-PUT",
                "option_symbol": "SPY  260320P00450000",
            }
        ],
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "decision_latest.json").write_text(json.dumps(artifact), encoding="utf-8")

    try:
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        app = _get_app()
        client = TestClient(app)
        r = client.get("/api/ui/universe")
        assert r.status_code == 200
        data = r.json()
        symbols = data.get("symbols") or []
        assert len(symbols) == 1
        row = symbols[0]
        assert row.get("symbol") == "SPY"
        assert row.get("verdict") == "ELIGIBLE"
        assert row.get("selected_contract_key") == "450-2026-03-20-PUT"
        assert row.get("option_symbol") == "SPY  260320P00450000"
        assert row.get("strike") == 450.0
    finally:
        reset_output_dir()


def test_eod_freeze_failure_writes_state_and_notification(tmp_path):
    """Phase 11.3: EOD freeze failure sets last_result=FAIL, last_error in state and appends EOD_FREEZE_FAILED."""
    pytest.importorskip("fastapi")
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    from app.api.server import _maybe_run_eod_freeze, _load_eod_freeze_state, _eod_freeze_state_path
    from app.api.notifications_store import load_notifications, _notifications_path

    et_tz = ZoneInfo("America/New_York")
    now_et = datetime(2026, 2, 17, 15, 59, 0, tzinfo=et_tz)

    state_path = tmp_path / "eod_freeze_state.json"
    notif_path = tmp_path / "notifications.jsonl"
    notif_path.parent.mkdir(parents=True, exist_ok=True)
    notif_path.write_text("")

    with patch("app.api.server._eod_freeze_state_path", return_value=state_path):
        with patch("app.api.server.get_market_phase", return_value="OPEN"):
            with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
                with patch("app.api.server.datetime") as mock_dt:
                    def _mock_now(tz=None):
                        if tz is timezone.utc or (tz is not None and "UTC" in str(tz)):
                            return now_et.astimezone(timezone.utc)
                        return now_et
                    mock_dt.now.side_effect = _mock_now
                    with patch("app.api.server.EOD_FREEZE_TIME_ET", "15:58"):
                        with patch("app.api.server.EOD_FREEZE_WINDOW_MINUTES", 10):
                            with patch("app.api.data_health.get_universe_symbols", return_value=["SPY"]):
                                with patch("app.core.eval.evaluation_service_v2.evaluate_universe") as mock_eval:
                                    mock_eval.side_effect = RuntimeError("Test failure")
                                    _maybe_run_eod_freeze(ZoneInfo)
    state = json.loads(state_path.read_text())
    assert state.get("last_result") == "FAIL"
    assert "Test failure" in (state.get("last_error") or "")

    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        notifs = load_notifications(limit=10)
    eod_fail = [n for n in notifs if n.get("subtype") == "EOD_FREEZE_FAILED" or n.get("type") == "EOD_FREEZE_FAILED"]
    assert len(eod_fail) >= 1
    assert "Test failure" in (eod_fail[0].get("message", ""))


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


def test_ui_notification_ack_append_event(tmp_path):
    """Phase 10.3: POST notifications/{id}/ack appends ack event; load merges ack_at_utc/ack_by."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    notif_path = tmp_path / "notifications.jsonl"
    notif_path.parent.mkdir(parents=True, exist_ok=True)
    app = _get_app()
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        from app.api.notifications_store import append_notification, load_notifications
        append_notification("WARN", "TEST", "msg", details={})
        items = load_notifications(10)
        assert len(items) == 1
        nid = items[0]["id"]
        client = TestClient(app)
        r = client.post(f"/api/ui/notifications/{nid}/ack")
    assert r.status_code == 200
    assert r.json().get("status") == "OK"
    assert "ack_at_utc" in r.json()
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        items2 = load_notifications(10)
    assert len(items2) == 1
    assert items2[0].get("ack_at_utc")
    assert items2[0].get("ack_by") == "ui"


def test_ui_scheduler_run_once_skipped_when_market_closed():
    """Phase 10.2: POST scheduler/run_once returns 200 with started=False when market closed."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    with patch("app.api.server.get_market_phase", return_value="POST"):
        client = TestClient(app)
        r = client.post("/api/ui/scheduler/run_once")
    assert r.status_code == 200
    data = r.json()
    assert "started" in data
    assert data["started"] is False
    assert "last_run_at" in data
    assert "last_result" in data


def test_ui_scheduler_run_once_success_when_market_open():
    """Phase 10.2: POST scheduler/run_once triggers eval and returns started=True when market open."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    # Patch where server looks up get_market_phase (imported in server namespace)
    with patch("app.api.server.get_market_phase", return_value="OPEN"):
        with patch("app.api.data_health.UNIVERSE_SYMBOLS", ["SPY"]):
            with patch("app.core.eval.universe_evaluator.trigger_evaluation") as mock_trigger:
                mock_trigger.return_value = {"started": True, "reason": "ok"}
                with patch("app.core.eval.universe_evaluator.get_evaluation_state", return_value={"evaluation_state": "IDLE"}):
                    client = TestClient(app)
                    r = client.post("/api/ui/scheduler/run_once")
    assert r.status_code == 200
    data = r.json()
    assert data["started"] is True
    assert "last_run_at" in data
    assert data["last_result"] == "OK"
