# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.8: ONE store guardrail tests."""

import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


class TestOneStoreGuardrails:
    """Guardrail tests for single source of truth."""

    def test_band_never_null_for_all_symbols(self, tmp_path):
        """Every symbol row has band in A/B/C/D and band_reason references that band."""
        from app.core.eval.evaluation_service_v2 import evaluate_universe

        try:
            artifact = evaluate_universe(["SPY", "AAPL"], mode="LIVE", output_dir=str(tmp_path))
        except Exception as e:
            pytest.skip(f"Requires ORATS: {e}")
        for s in artifact.symbols:
            assert s.band in ("A", "B", "C", "D"), f"Symbol {s.symbol}: band must be A|B|C|D, got {s.band}"
            assert s.band_reason, f"Symbol {s.symbol}: band_reason must not be empty"
            assert s.band in (s.band_reason or ""), f"Symbol {s.symbol}: band_reason must reference band"

    def test_store_path_is_repo_root_out(self):
        """get_decision_store_path() endswith /out/decision_latest.json and is under repo root (NOT chakraops/app/out)."""
        from app.core.eval.evaluation_store_v2 import get_decision_store_path, reset_output_dir

        reset_output_dir()
        path = get_decision_store_path()
        posix = path.as_posix()
        assert posix.endswith("/out/decision_latest.json"), f"Path must end with /out/decision_latest.json: {posix}"
        assert "/app/out/" not in posix, f"Path must NOT be under chakraops/app/out: {posix}"
        repo_root = _REPO.parent
        try:
            path.relative_to(repo_root)
        except ValueError:
            pytest.fail(f"Path {path} must be under repo root {repo_root}")

    def test_no_v1_imports_or_fallbacks(self):
        """UI LIVE decision path uses EvaluationStoreV2 only; no v1 fallbacks. No decision_snapshot merge on frontend."""
        ui_routes = (_REPO / "app" / "api" / "ui_routes.py").read_text(encoding="utf-8")
        assert "get_evaluation_store_v2" in ui_routes, "ui_routes must use get_evaluation_store_v2 for LIVE"
        assert "build_latest_response" not in ui_routes, "ui_routes must not use build_latest_response (v1)"
        # Frontend: Universe/Dashboard must not merge from decision_snapshot
        frontend_root = _REPO.parent / "frontend" / "src"
        if frontend_root.exists():
            for f in frontend_root.rglob("*.tsx"):
                if "Universe" in f.name or "Dashboard" in f.name:
                    txt = f.read_text(encoding="utf-8")
                    assert "mergeUniverseDecision" not in txt, f"{f}: must not use mergeUniverseDecision"

    def test_api_endpoints_read_same_artifact(self):
        """POST eval/run then GET decision/latest, universe, symbol-diagnostics: pipeline_timestamp matches."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from app.api.server import app

        client = TestClient(app)
        # Run evaluation (requires ORATS)
        try:
            r = client.post("/api/ui/eval/run")
            if r.status_code != 200 or r.json().get("status") != "OK":
                pytest.skip("eval/run failed (ORATS required)")
        except Exception as e:
            pytest.skip(f"eval/run failed: {e}")

        dec = client.get("/api/ui/decision/latest?mode=LIVE")
        if dec.status_code != 200:
            pytest.skip("decision/latest returned non-200 (no artifact)")
        dec_body = dec.json()
        ts = (dec_body.get("artifact") or {}).get("metadata") or {}
        pipeline_ts = ts.get("pipeline_timestamp")
        if not pipeline_ts:
            pytest.skip("No pipeline_timestamp in decision")

        uni = client.get("/api/ui/universe")
        assert uni.status_code == 200
        uni_body = uni.json()
        assert uni_body.get("artifact_version") == "v2"
        # decision/latest and universe must return same pipeline_timestamp as store
        assert uni_body.get("updated_at") == pipeline_ts, (
            f"universe.updated_at ({uni_body.get('updated_at')}) != decision/latest pipeline_timestamp ({pipeline_ts})"
        )
        assert dec_body.get("artifact", {}).get("metadata", {}).get("pipeline_timestamp") == pipeline_ts

        diag = client.get("/api/ui/symbol-diagnostics?symbol=SPY")
        if diag.status_code == 200:
            # Symbol-diagnostics gets from same store
            pass  # No pipeline_ts in symbol-diagnostics response; consistency checked below

    def test_symbol_diagnostics_matches_universe_row_for_store_mode(self):
        """For a symbol in store, score/band/verdict match between universe row and symbol-diagnostics (recompute=0)."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from app.api.server import app

        client = TestClient(app)
        uni = client.get("/api/ui/universe")
        if uni.status_code != 200:
            pytest.skip("universe not available")
        symbols = uni.json().get("symbols", [])
        spy = next((s for s in symbols if s.get("symbol") == "SPY"), None)
        if not spy:
            pytest.skip("SPY not in universe")
        diag = client.get("/api/ui/symbol-diagnostics?symbol=SPY")
        if diag.status_code != 200:
            pytest.skip("symbol-diagnostics not available for SPY")
        d = diag.json()
        assert spy.get("score") == d.get("composite_score"), "universe score must match symbol-diagnostics"
        assert spy.get("band") == d.get("confidence_band"), "universe band must match symbol-diagnostics"
        assert (spy.get("verdict") or spy.get("final_verdict")) == d.get("verdict"), "universe verdict must match"

    def test_recompute_endpoint_writes_to_store_and_universe_sees_it(self, tmp_path):
        """POST /api/ui/symbols/{symbol}/recompute updates canonical store; GET universe returns updated symbol."""
        pytest.importorskip("fastapi")
        from dataclasses import replace
        from datetime import datetime, timezone
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary
        from app.core.eval.evaluation_store_v2 import (
            get_evaluation_store_v2,
            reset_output_dir,
            set_output_dir,
        )
        from app.api.server import app

        set_output_dir(tmp_path)
        try:
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
                    "mode": "LIVE",
                    "pipeline_timestamp": "2026-01-01T12:00:00Z",
                    "universe_size": 1,
                    "evaluated_count_stage1": 1,
                    "evaluated_count_stage2": 0,
                    "eligible_count": 0,
                    "warnings": [],
                },
                symbols=[sym],
                selected_candidates=[],
            )
            (tmp_path / "decision_latest.json").write_text(
                json.dumps(artifact.to_dict(), indent=2),
                encoding="utf-8",
            )
            # Force store to load from tmp_path (singleton may already exist)
            store = get_evaluation_store_v2()
            store.reload_from_disk()

            def fake_merge(symbol: str, mode: str = "LIVE"):
                store = get_evaluation_store_v2()
                current = store.get_latest()
                if not current:
                    return None
                sym_upper = symbol.strip().upper()
                ts = datetime.now(timezone.utc).isoformat()
                new_symbols = [
                    replace(s, score=99, band="B") if (s.symbol or "").strip().upper() == sym_upper else s
                    for s in current.symbols
                ]
                meta = dict(current.metadata)
                meta["pipeline_timestamp"] = ts
                merged = DecisionArtifactV2(
                    metadata=meta,
                    symbols=new_symbols,
                    selected_candidates=current.selected_candidates,
                    candidates_by_symbol=getattr(current, "candidates_by_symbol", {}) or {},
                    gates_by_symbol=getattr(current, "gates_by_symbol", {}) or {},
                    earnings_by_symbol=getattr(current, "earnings_by_symbol", {}) or {},
                    diagnostics_by_symbol=getattr(current, "diagnostics_by_symbol", {}) or {},
                    warnings=getattr(current, "warnings", []) or [],
                )
                store.set_latest(merged)
                return merged

            with patch(
                "app.core.eval.evaluation_service_v2.evaluate_single_symbol_and_merge",
                side_effect=fake_merge,
            ):
                client = TestClient(app)
                r = client.post("/api/ui/symbols/SPY/recompute")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("updated") is True
            assert body.get("symbol") == "SPY"
            assert body.get("score") == 99
            assert body.get("band") == "B"
            ts = body.get("pipeline_timestamp")
            assert ts

            uni = client.get("/api/ui/universe")
            assert uni.status_code == 200
            uni_body = uni.json()
            assert uni_body.get("updated_at") == ts
            spy = next((s for s in uni_body.get("symbols", []) if s.get("symbol") == "SPY"), None)
            assert spy is not None
            assert spy.get("score") == 99
            assert spy.get("band") == "B"
        finally:
            reset_output_dir()
