# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 11.2: Decision history retention and exact run fetch tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_decision_history_written(tmp_path):
    """Phase 11.2: After store.set_latest, run_id history file exists at out/decisions/{symbol}/{run_id}.json."""
    from app.core.eval.evaluation_store_v2 import (
        set_output_dir,
        reset_output_dir,
        get_evaluation_store_v2,
        _history_path,
    )
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary

    run_id = "test-run-1111-2222-3333-444455556666"
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

    try:
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.set_latest(artifact)
        hist_path = _history_path("SPY", run_id)
        assert hist_path.exists(), f"Expected history file at {hist_path}"
        import json
        with open(hist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("metadata", {}).get("run_id") == run_id
    finally:
        reset_output_dir()


def test_decision_history_retention(tmp_path):
    """Phase 11.2: Write > N runs; ensure only N remain per symbol."""
    from app.core.eval.evaluation_store_v2 import (
        set_output_dir,
        reset_output_dir,
        get_evaluation_store_v2,
        DECISION_HISTORY_KEEP,
        _history_dir,
    )
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary

    keep = 3  # use small N for test
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

    try:
        set_output_dir(tmp_path)
        with patch("app.core.eval.evaluation_store_v2.DECISION_HISTORY_KEEP", keep):
            store = get_evaluation_store_v2()
            for i in range(keep + 2):
                run_id = f"run-{i:04d}-1111-2222-3333-444455556666"
                meta = {
                    "artifact_version": "v2",
                    "pipeline_timestamp": f"2026-02-17T21:{i:02d}:00Z",
                    "run_id": run_id,
                }
                art = DecisionArtifactV2(metadata=meta, symbols=[sym], selected_candidates=[])
                store.set_latest(art)
            sym_dir = _history_dir() / "SPY"
            assert sym_dir.exists()
            files = list(sym_dir.glob("*.json"))
            assert len(files) <= keep, f"Expected at most {keep} files, got {len(files)}"
    finally:
        reset_output_dir()


def test_ui_decision_fetch_exact_run(tmp_path):
    """Phase 11.2: GET /api/ui/decision?symbol=SPY&run_id=UUID returns correct artifact from history."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.core.eval.evaluation_store_v2 import (
        set_output_dir,
        reset_output_dir,
        get_evaluation_store_v2,
    )
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary

    run_id = "exact-fetch-run-1111-2222-3333-444455556666"
    sym = SymbolEvalSummary(
        symbol="SPY",
        verdict="ELIGIBLE",
        final_verdict="ELIGIBLE",
        score=88,
        band="A",
        primary_reason="exact run test",
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

    try:
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.set_latest(artifact)

        from app.api.server import app
        client = TestClient(app)
        r = client.get(f"/api/ui/decision?symbol=SPY&run_id={run_id}")
        assert r.status_code == 200
        data = r.json()
        assert data.get("exact_run") is True
        assert data.get("run_id") == run_id
        assert data.get("artifact", {}).get("metadata", {}).get("run_id") == run_id
        symbols = data.get("artifact", {}).get("symbols", [])
        assert len(symbols) == 1
        assert symbols[0].get("symbol") == "SPY"
        assert symbols[0].get("score") == 88
    finally:
        reset_output_dir()


def test_ui_decision_fetch_exact_run_404_when_missing():
    """Phase 11.2: GET /api/ui/decision?symbol=SPY&run_id=... returns 404 when history file missing."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    r = client.get("/api/ui/decision?symbol=SPY&run_id=nonexistent-run-1111-2222-3333-444455556666")
    assert r.status_code == 404
    assert "exact run not found" in (r.json().get("detail") or "").lower() or "not found" in (r.json().get("detail") or "").lower()
