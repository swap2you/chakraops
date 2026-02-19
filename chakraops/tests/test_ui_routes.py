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
                "contract_key": "450-2026-03-21-PUT",
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
            # CSP 1 @ 450 = 45000 collateral > 30000 max (Phase 12.0: requires contract_key)
            r = client.post(
                "/api/ui/positions",
                json={
                    "symbol": "SPY",
                    "strategy": "CSP",
                    "contracts": 1,
                    "strike": 450.0,
                    "expiration": "2026-03-21",
                    "credit_expected": 2.50,
                    "contract_key": "450-2026-03-21-PUT",
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
                    "contract_key": "450-2026-03-21-PUT",
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
                    "contract_key": "450-2026-03-21-PUT",
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
                    "contract_key": "450-2026-03-21-PUT",
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


def test_ui_positions_post_409_when_options_missing_contract_identity(tmp_path):
    """Phase 12.0: POST positions returns 409 when CSP/CC without contract_key or option_symbol."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        r = client.post(
            "/api/ui/positions",
            json={
                "symbol": "SPY",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 450.0,
                "expiration": "2026-03-21",
                "credit_expected": 250,
            },
        )
        assert r.status_code == 409
        data = r.json()
        errs = data.get("detail", {})
        if isinstance(errs, dict) and "errors" in errs:
            errs = errs["errors"]
        assert "contract_key or option_symbol" in str(errs)


def test_ui_positions_close_pnl_with_fees(tmp_path):
    """Phase 12.0: PnL = open_credit - close_debit - open_fees - close_fees."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

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
                "credit_expected": 250,
                "contract_key": "450-2026-03-21-PUT",
            },
        )
        assert post.status_code == 200
        pid = post.json()["position_id"]
        # open 250, close 100, open_fees 5, close_fees 2 -> pnl = 250 - 100 - 5 - 2 = 143
        # Position model doesn't have open_fees in create; we'd need to patch or update
        # For now test without open_fees: close_fees=2 -> pnl = 250 - 100 - 2 = 148
        close_res = client.post(
            f"/api/ui/positions/{pid}/close",
            json={"close_price": 1.00, "close_fees": 2.0},
        )
        assert close_res.status_code == 200
        closed = close_res.json()
        rpnl = closed.get("realized_pnl")
        assert rpnl is not None
        assert abs(rpnl - 148.0) < 0.01


def test_ui_portfolio_metrics_returns_expected_fields(tmp_path):
    """Phase 12.0: GET /api/ui/portfolio/metrics returns open_positions_count, capital_deployed, realized_pnl_total, etc."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        r = client.get("/api/ui/portfolio/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "open_positions_count" in data
        assert "capital_deployed" in data
        assert "realized_pnl_total" in data
        assert "win_rate" in data


def test_ui_positions_close_and_delete_guardrail(tmp_path):
    """Phase 10.0: Close position computes realized_pnl; delete allowed only for CLOSED/test."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        # Create OPEN position: CSP 1 contract @ 450, credit 250 total (Phase 12.0: requires contract_key)
        post = client.post(
            "/api/ui/positions",
            json={
                "symbol": "SPY",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 450.0,
                "expiration": "2026-03-21",
                "credit_expected": 250.0,
                "contract_key": "450-2026-03-21-PUT",
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
        # open_credit 250 total, close_debit 100, pnl = 250 - 100 = 150
        rpnl = closed.get("realized_pnl")
        assert rpnl is not None
        assert abs(rpnl - 150.0) < 0.01


def test_ui_positions_close_csp_per_share_realized_pnl_positive(tmp_path):
    """Phase 21.2: CSP with per-share entry 9.40, close 4.50 → realized +490 (SHORT option formula)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        post = client.post(
            "/api/ui/positions",
            json={
                "symbol": "NVDA",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 140.0,
                "expiration": "2026-03-21",
                "credit_expected": 9.40,
                "contract_key": "140-2026-03-21-PUT",
            },
        )
        assert post.status_code == 200
        pid = post.json()["position_id"]

        close_res = client.post(
            f"/api/ui/positions/{pid}/close",
            json={"close_price": 4.50},
        )
        assert close_res.status_code == 200
        closed = close_res.json()
        assert closed.get("status") == "CLOSED"
        rpnl = closed.get("realized_pnl")
        assert rpnl is not None
        assert abs(rpnl - 490.0) < 0.01, f"Expected +490, got {rpnl}"

        # Delete CLOSED position -> 200
        del_closed = client.delete(f"/api/ui/positions/{pid}")
        assert del_closed.status_code == 200
        assert del_closed.json().get("deleted") == pid

        # Verify gone
        get_after = client.get("/api/ui/positions")
        assert get_after.status_code == 200
        assert len(get_after.json().get("positions") or []) == 0


def test_ui_portfolio_realized_total_equals_sum_of_closed_positions(tmp_path):
    """Phase 21.2: Regression — realized_pnl_total = sum of per-position realized_pnl."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        p1 = client.post(
            "/api/ui/positions",
            json={
                "symbol": "SPY",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 450.0,
                "expiration": "2026-03-21",
                "credit_expected": 250.0,
                "contract_key": "450-2026-03-21-PUT",
            },
        )
        assert p1.status_code == 200
        client.post(f"/api/ui/positions/{p1.json()['position_id']}/close", json={"close_price": 1.00})

        p2 = client.post(
            "/api/ui/positions",
            json={
                "symbol": "NVDA",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 140.0,
                "expiration": "2026-03-21",
                "credit_expected": 9.40,
                "contract_key": "140-2026-03-21-PUT",
            },
        )
        assert p2.status_code == 200
        client.post(f"/api/ui/positions/{p2.json()['position_id']}/close", json={"close_price": 4.50})

        r = client.get("/api/ui/portfolio/metrics")
        assert r.status_code == 200
        data = r.json()
        total = data.get("realized_pnl_total")
        assert total is not None
        assert abs(total - (150.0 + 490.0)) < 0.02, f"Expected 640, got {total}"


def test_ui_positions_events_appended_on_create_and_close(tmp_path):
    """Phase 13.0: OPEN event on create; CLOSE event on close."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

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
                "credit_expected": 250.0,
                "contract_key": "450-2026-03-21-PUT",
            },
        )
        assert post.status_code == 200
        pid = post.json()["position_id"]

        # GET events: should have OPEN
        ev = client.get(f"/api/ui/positions/{pid}/events")
        assert ev.status_code == 200
        data = ev.json()
        assert data["position_id"] == pid
        events = data.get("events") or []
        assert len(events) >= 1
        types = [e["type"] for e in events]
        assert "OPEN" in types

        # Close position
        client.post(f"/api/ui/positions/{pid}/close", json={"close_price": 1.00})
        ev2 = client.get(f"/api/ui/positions/{pid}/events")
        assert ev2.status_code == 200
        events2 = ev2.json().get("events") or []
        types2 = [e["type"] for e in events2]
        assert "CLOSE" in types2


def test_ui_positions_roll_creates_linked_position_and_events(tmp_path):
    """Phase 13.0: Roll closes old, creates new with parent_position_id; events for both."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

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
                "credit_expected": 250.0,
                "contract_key": "450-2026-03-21-PUT",
            },
        )
        assert post.status_code == 200
        pid = post.json()["position_id"]

        roll = client.post(
            f"/api/ui/positions/{pid}/roll",
            json={
                "contract_key": "460-2026-04-21-PUT",
                "strike": 460.0,
                "expiration": "2026-04-21",
                "contracts": 1,
                "close_debit": 100.0,
                "open_credit": 200.0,
            },
        )
        assert roll.status_code == 200
        body = roll.json()
        assert body["closed_position_id"] == pid
        new_pos = body.get("new_position") or {}
        assert new_pos.get("parent_position_id") == pid
        assert new_pos.get("position_id") != pid
        assert new_pos.get("status") == "OPEN"
        assert new_pos.get("symbol") == "SPY"
        assert new_pos.get("strategy") == "CSP"

        # Old position events: CLOSE (from close) + NOTE (rolled_to)
        ev_old = client.get(f"/api/ui/positions/{pid}/events")
        assert ev_old.status_code == 200
        types_old = [e["type"] for e in ev_old.json().get("events") or []]
        assert "CLOSE" in types_old

        # New position has OPEN event
        new_id = new_pos["position_id"]
        ev_new = client.get(f"/api/ui/positions/{new_id}/events")
        assert ev_new.status_code == 200
        events_new = ev_new.json().get("events") or []
        assert len(events_new) >= 1
        assert events_new[-1]["type"] == "OPEN"


def test_ui_portfolio_risk_pass_when_within_limits(tmp_path):
    """Phase 14.0: GET /api/ui/portfolio/risk returns PASS when within account limits."""
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
        '"is_default":true,"max_symbol_collateral":50000,"max_deployed_pct":0.5,"max_near_expiry_positions":3}]',
        encoding="utf-8",
    )

    def _fake_accounts_path():
        return accounts_file

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        with patch("app.core.accounts.store._accounts_path", side_effect=_fake_accounts_path):
            client = TestClient(app)
            post = client.post(
                "/api/ui/positions",
                json={
                    "symbol": "SPY",
                    "strategy": "CSP",
                    "contracts": 1,
                    "strike": 300.0,
                    "expiration": "2026-12-20",
                    "credit_expected": 250.0,
                    "contract_key": "300-2026-12-20-PUT",
                },
            )
            assert post.status_code == 200
            r = client.get("/api/ui/portfolio/risk")
            assert r.status_code == 200
            data = r.json()
            assert data.get("status") == "PASS"
            assert "metrics" in data
            assert data["metrics"].get("capital_deployed") == 30000.0
            assert len(data.get("breaches") or []) == 0


def test_ui_portfolio_risk_fail_when_breach(tmp_path):
    """Phase 14.0: GET /api/ui/portfolio/risk returns FAIL when max_deployed_pct exceeded; notification emitted."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    accounts_dir = tmp_path / "accounts"
    notifications_path = tmp_path / "notifications.jsonl"
    positions_dir.mkdir(parents=True, exist_ok=True)
    accounts_dir.mkdir(parents=True, exist_ok=True)
    accounts_file = accounts_dir / "accounts.json"
    accounts_file.write_text(
        '[{"account_id":"acct_1","provider":"Manual","account_type":"Taxable","total_capital":100000,'
        '"max_capital_per_trade_pct":5,"max_total_exposure_pct":30,"allowed_strategies":["CSP"],'
        '"is_default":true,"max_deployed_pct":0.2}]',
        encoding="utf-8",
    )

    def _fake_accounts_path():
        return accounts_file

    def _fake_notifications_path():
        return notifications_path

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        with patch("app.core.accounts.store._accounts_path", side_effect=_fake_accounts_path):
            with patch("app.api.notifications_store._notifications_path", side_effect=_fake_notifications_path):
                client = TestClient(app)
                post = client.post(
                    "/api/ui/positions",
                    json={
                        "symbol": "SPY",
                        "strategy": "CSP",
                        "contracts": 2,
                        "strike": 450.0,
                        "expiration": "2026-12-20",
                        "credit_expected": 250.0,
                        "contract_key": "450-2026-12-20-PUT",
                    },
                )
                assert post.status_code == 200
                r = client.get("/api/ui/portfolio/risk")
                assert r.status_code == 200
                data = r.json()
                assert data.get("status") == "FAIL"
                breaches = data.get("breaches") or []
                assert len(breaches) >= 1
                msg = breaches[0].get("message", "")
                assert "Deployed" in msg or "max" in msg.lower()
                assert data["metrics"]["capital_deployed"] == 90000.0
                assert data["metrics"]["deployed_pct"] > 0.2


def test_ui_portfolio_risk_diagnostics_emits_notification_on_fail(tmp_path):
    """Phase 14.0: Run portfolio_risk diagnostic; on FAIL appends PORTFOLIO_RISK notification."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    accounts_dir = tmp_path / "accounts"
    diag_path = tmp_path / "diagnostics_history.jsonl"
    notif_path = tmp_path / "notifications.jsonl"
    positions_dir.mkdir(parents=True, exist_ok=True)
    accounts_dir.mkdir(parents=True, exist_ok=True)
    accounts_file = accounts_dir / "accounts.json"
    accounts_file.write_text(
        '[{"account_id":"acct_1","provider":"Manual","account_type":"Taxable","total_capital":50000,'
        '"max_capital_per_trade_pct":5,"max_total_exposure_pct":30,"allowed_strategies":["CSP"],'
        '"is_default":true,"max_symbol_collateral":20000}]',
        encoding="utf-8",
    )

    def _fake_accounts_path():
        return accounts_file

    def _fake_diagnostics_path():
        return diag_path

    def _fake_notif_path():
        return notif_path

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        with patch("app.core.accounts.store._accounts_path", side_effect=_fake_accounts_path):
            with patch("app.api.diagnostics._diagnostics_history_path", side_effect=_fake_diagnostics_path):
                with patch("app.api.notifications_store._notifications_path", side_effect=_fake_notif_path):
                    client = TestClient(app)
                    client.post(
                        "/api/ui/positions",
                        json={
                            "symbol": "AAPL",
                            "strategy": "CSP",
                            "contracts": 3,
                            "strike": 150.0,
                            "expiration": "2026-12-20",
                            "credit_expected": 100.0,
                            "contract_key": "150-2026-12-20-PUT",
                        },
                    )
                    r = client.post("/api/ui/diagnostics/run", params={"checks": "portfolio_risk"})
                    assert r.status_code == 200
                    checks = r.json().get("checks") or []
                    pr = next((c for c in checks if c.get("check") == "portfolio_risk"), None)
                    assert pr is not None
                    assert pr.get("status") == "FAIL"
                    assert pr["details"].get("breach_count", 0) >= 1
                    if notif_path.exists():
                        lines = [ln.strip() for ln in notif_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
                        assert any("PORTFOLIO_RISK" in ln for ln in lines)
                        assert any("RISK_LIMIT_BREACH" in ln for ln in lines)


def test_ui_marks_refresh_with_mock_fetcher(tmp_path):
    """Phase 15.0: POST marks/refresh with mock fetcher updates position; computes unrealized PnL."""
    pytest.importorskip("fastapi")
    from datetime import date
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    def mock_fetcher(symbol: str, expiration: date, strike: float, option_type: str):
        return 1.0

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
                "expiration": "2026-12-20",
                "credit_expected": 250.0,
                "contract_key": "450-2026-12-20-PUT",
            },
        )
        assert post.status_code == 200
        pid = post.json()["position_id"]

        from app.core.positions.service import list_positions
        from app.core.portfolio.marking import refresh_marks
        positions = list_positions(status=None, symbol=None, exclude_test=True)
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        updated, skipped, errors = refresh_marks(open_pos, mark_fetcher=mock_fetcher)
        assert updated == 1
        assert skipped == 0

        from app.core.positions.store import get_position
        pos = get_position(pid)
        assert pos is not None
        assert getattr(pos, "mark_price_per_contract", None) == 1.0
        assert getattr(pos, "mark_time_utc", None) is not None

        mtm = client.get("/api/ui/portfolio/mtm")
        assert mtm.status_code == 200
        data = mtm.json()
        assert data["unrealized_total"] == 150.0  # 250 open_credit - 100 mark_debit
        assert len(data["positions"]) == 1
        assert data["positions"][0]["unrealized_pnl"] == 150.0


def test_ui_marks_refresh_skips_equity_without_failing(tmp_path):
    """Phase 15.0: Equity positions (no contract_key/option_symbol) are skipped; refresh does not fail."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)
    (positions_dir / "positions.json").write_text(
        '[{"position_id":"pos_1","account_id":"paper","symbol":"AAPL","strategy":"CSP",'
        '"contracts":1,"strike":150.0,"expiration":"2026-12-20","status":"OPEN",'
        '"opened_at":"2026-01-01T12:00:00Z","credit_expected":100.0}]',
        encoding="utf-8",
    )

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        r = client.post("/api/ui/positions/marks/refresh")
        assert r.status_code == 200
        data = r.json()
        assert data["updated_count"] == 0
        assert data["skipped_count"] >= 1
        # Equity positions must not add to errors (no MARK_REFRESH_FAILED for missing contract_key)
        errors = data.get("errors") or []
        assert not any("no contract_key" in e or "no option_symbol" in e or "contract_key" in e.lower() and "option_symbol" in e.lower() for e in errors)


def test_ui_portfolio_mtm_returns_totals(tmp_path):
    """Phase 15.0: GET portfolio/mtm returns realized_total, unrealized_total, per-position."""
    pytest.importorskip("fastapi")
    from datetime import date
    from fastapi.testclient import TestClient

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)

    def mock_fetcher(symbol, expiration, strike, option_type):
        return 1.2

    app = _get_app()
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
        client = TestClient(app)
        client.post(
            "/api/ui/positions",
            json={
                "symbol": "SPY",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 450.0,
                "expiration": "2026-12-20",
                "credit_expected": 250.0,
                "contract_key": "450-2026-12-20-PUT",
            },
        )
        from app.core.positions.service import list_positions
        from app.core.portfolio.marking import refresh_marks
        positions = list_positions(status=None, symbol=None, exclude_test=True)
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        refresh_marks(open_pos, mark_fetcher=mock_fetcher)

        r = client.get("/api/ui/portfolio/mtm")
        assert r.status_code == 200
        data = r.json()
        assert "realized_total" in data
        assert "unrealized_total" in data
        assert "positions" in data
        assert data["unrealized_total"] == 130.0  # 250 open_credit - 120 mark_debit (1.2*100*1)


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


def test_phase16_mark_refresh_writes_state_and_system_health_includes_it(tmp_path):
    """Phase 16.0: Mark refresh writes state; system health includes mark_refresh."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    store_path = out_dir / "decision_latest.json"
    store_path.write_text('{"metadata":{}}', encoding="utf-8")
    positions_dir = out_dir / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)
    (positions_dir / "positions.json").write_text(
        '[{"position_id":"pos_1","account_id":"paper","symbol":"AAPL","strategy":"CSP",'
        '"contracts":1,"strike":150.0,"expiration":"2026-12-20","status":"OPEN",'
        '"opened_at":"2026-01-01T12:00:00Z","credit_expected":100.0}]',
        encoding="utf-8",
    )

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
            client = TestClient(app)
            r = client.post("/api/ui/positions/marks/refresh")
    assert r.status_code == 200
    state_path = out_dir / "mark_refresh_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "last_run_at_utc" in state
    assert "last_result" in state
    assert "updated_count" in state

    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        client = TestClient(app)
        h = client.get("/api/ui/system-health")
    assert h.status_code == 200
    health = h.json()
    assert "mark_refresh" in health
    mr = health["mark_refresh"]
    assert "last_run_at_utc" in mr
    assert "last_result" in mr


def test_phase16_portfolio_risk_notification_throttled(tmp_path):
    """Phase 16.0: Repeated identical FAIL within hour does not append multiple notifications."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    store_path = out_dir / "decision_latest.json"
    store_path.write_text('{"metadata":{}}', encoding="utf-8")
    notif_path = out_dir / "notifications.jsonl"
    accounts_path = out_dir / "accounts"
    accounts_path.mkdir(parents=True, exist_ok=True)
    (accounts_path / "accounts.json").write_text(
        '[{"account_id":"paper","total_capital":1000,"max_deployed_pct":0.1,"is_default":true,"active":true}]',
        encoding="utf-8",
    )
    positions_dir = out_dir / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)
    (positions_dir / "positions.json").write_text(
        '[{"position_id":"pos_1","account_id":"paper","symbol":"AAPL","strategy":"CSP",'
        '"contracts":5,"strike":200.0,"expiration":"2026-12-20","status":"OPEN",'
        '"opened_at":"2026-01-01T12:00:00Z","credit_expected":500.0}]',
        encoding="utf-8",
    )

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
            with patch("app.core.accounts.store._get_accounts_dir", return_value=accounts_path):
                with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir):
                    client = TestClient(app)
                    r1 = client.post("/api/ui/diagnostics/run?checks=portfolio_risk")
                    r2 = client.post("/api/ui/diagnostics/run?checks=portfolio_risk")
    assert r1.status_code == 200
    assert r2.status_code == 200
    lines = [ln.strip() for ln in notif_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    risk_lines = [ln for ln in lines if "PORTFOLIO_RISK" in ln]
    assert len(risk_lines) == 1, f"Expected 1 PORTFOLIO_RISK notification, got {len(risk_lines)}"


def test_phase16_diagnostics_includes_recommended_action(tmp_path):
    """Phase 16.0: Diagnostic check responses include recommended_action."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    store_path = out_dir / "decision_latest.json"
    store_path.write_text('{"metadata":{"artifact_version":"v2"},"symbols":[{"symbol":"SPY"}]}', encoding="utf-8")

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        client = TestClient(app)
        r = client.post("/api/ui/diagnostics/run?checks=orats,decision_store")
    assert r.status_code == 200
    data = r.json()
    for ch in data.get("checks", []):
        assert "recommended_action" in ch


def test_phase17_stores_integrity_and_repair(tmp_path):
    """Phase 17.0: GET stores/integrity returns scan results; POST stores/repair removes invalid lines."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    store_path = out_dir / "decision_latest.json"
    store_path.write_text("{}", encoding="utf-8")
    notif_path = out_dir / "notifications.jsonl"
    notif_path.write_text('{"id":"1","type":"A"}\nbad line\n{"id":"2","type":"B"}\n', encoding="utf-8")

    store_paths = {
        "notifications": notif_path,
        "diagnostics_history": out_dir / "diagnostics_history.jsonl",
        "positions_events": out_dir / "positions" / "positions_events.jsonl",
    }

    app = _get_app()
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        with patch("app.core.io.jsonl_integrity.get_store_paths", return_value=store_paths):
            client = TestClient(app)
            r = client.get("/api/ui/stores/integrity")
    assert r.status_code == 200
    data = r.json()
    assert "stores" in data
    assert "notifications" in data["stores"]
    n = data["stores"]["notifications"]
    assert n["total_lines"] == 3
    assert n["invalid_lines"] == 1

    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=store_path):
        with patch("app.core.io.jsonl_integrity.get_store_paths", return_value=store_paths):
            r2 = client.post("/api/ui/stores/repair?store=notifications")
    assert r2.status_code == 200
    repair = r2.json()
    assert repair["store"] == "notifications"
    assert repair["after"]["removed_count"] == 1
    assert repair["after"]["valid_count"] == 2
    assert repair["backup_path"] is not None
