# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market live guardrail tests: one store, endpoint consistency, score/band, schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


class TestMarketLiveStoreGuardrails:
    """Store file and schema invariants (no real ORATS)."""

    def test_market_live_store_has_required_fields(self, tmp_path):
        """Store JSON has artifact_version v2, metadata.pipeline_timestamp, symbols with band/band_reason."""
        from app.core.eval.evaluation_store_v2 import (
            get_decision_store_path,
            set_output_dir,
            reset_output_dir,
        )
        from app.core.eval.decision_artifact_v2 import (
            DecisionArtifactV2,
            SymbolEvalSummary,
            assign_band,
            assign_band_reason,
        )

        set_output_dir(tmp_path)
        try:
            symbols = [
                SymbolEvalSummary(
                    symbol="SPY",
                    verdict="HOLD",
                    final_verdict="HOLD",
                    score=50,
                    band=assign_band(50),
                    primary_reason="test",
                    stage_status="RUN",
                    stage1_status="PASS",
                    stage2_status="NOT_RUN",
                    provider_status="OK",
                    data_freshness=None,
                    evaluated_at="2026-01-01T12:00:00Z",
                    strategy=None,
                    price=450.0,
                    expiration=None,
                    has_candidates=False,
                    candidate_count=0,
                    band_reason=assign_band_reason(50),
                ),
            ]
            artifact = DecisionArtifactV2(
                metadata={
                    "artifact_version": "v2",
                    "pipeline_timestamp": "2026-01-01T12:00:00Z",
                    "market_phase": "OPEN",
                },
                symbols=symbols,
                selected_candidates=[],
            )
            from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
            store = get_evaluation_store_v2()
            store.set_latest(artifact)

            path = get_decision_store_path()
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.get("metadata") or {}
            assert meta.get("artifact_version") == "v2"
            assert meta.get("pipeline_timestamp")
            syms = data.get("symbols") or []
            assert len(syms) >= 1
            for s in syms:
                assert s.get("band") in ("A", "B", "C", "D")
                assert s.get("band_reason")
        finally:
            reset_output_dir()

    def test_system_health_reports_decision_store_critical_when_invalid(self, tmp_path):
        """system-health decision_store is CRITICAL when artifact_version != v2."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from app.api.server import app
        from app.core.eval.evaluation_store_v2 import (
            set_output_dir,
            reset_output_dir,
            get_evaluation_store_v2,
        )
        from app.core.eval.decision_artifact_v2 import (
            DecisionArtifactV2,
            SymbolEvalSummary,
            assign_band,
        )

        set_output_dir(tmp_path)
        try:
            store = get_evaluation_store_v2()
            sym = SymbolEvalSummary(
                symbol="X",
                verdict="HOLD",
                final_verdict="HOLD",
                score=0,
                band="D",
                primary_reason="x",
                stage_status="NOT_RUN",
                stage1_status="NOT_RUN",
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
            art = DecisionArtifactV2(
                metadata={"artifact_version": "v1", "pipeline_timestamp": "2026-01-01T00:00:00Z"},
                symbols=[sym],
                selected_candidates=[],
            )
            store.set_latest(art)
            client = TestClient(app)
            r = client.get("/api/ui/system-health")
            assert r.status_code == 200
            body = r.json()
            ds = body.get("decision_store") or {}
            assert ds.get("status") == "CRITICAL"
            assert "v2" in (ds.get("reason") or "").lower() or "artifact" in (ds.get("reason") or "").lower()
        finally:
            reset_output_dir()


class TestUniverseAndSymbolDiagnosticsConsistency:
    """Universe row vs symbol-diagnostics consistency using store (mock artifact)."""

    def test_universe_and_symbol_diagnostics_consistency_using_store(self, tmp_path):
        """With fixture artifact in store, universe row and symbol-diagnostics match score/band for same symbol."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from app.api.server import app
        from app.core.eval.evaluation_store_v2 import (
            set_output_dir,
            reset_output_dir,
            get_evaluation_store_v2,
        )
        from app.core.eval.decision_artifact_v2 import (
            DecisionArtifactV2,
            SymbolEvalSummary,
            assign_band,
            assign_band_reason,
        )

        set_output_dir(tmp_path)
        try:
            symbols = [
                SymbolEvalSummary(
                    symbol="SPY",
                    verdict="HOLD",
                    final_verdict="HOLD",
                    score=72,
                    band=assign_band(72),
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
                    band_reason=assign_band_reason(72),
                ),
            ]
            artifact = DecisionArtifactV2(
                metadata={"artifact_version": "v2", "pipeline_timestamp": "2026-01-01T12:00:00Z"},
                symbols=symbols,
                selected_candidates=[],
            )
            store = get_evaluation_store_v2()
            store.set_latest(artifact)

            client = TestClient(app)
            uni = client.get("/api/ui/universe")
            assert uni.status_code == 200
            uni_symbols = uni.json().get("symbols") or []
            spy_uni = next((s for s in uni_symbols if s.get("symbol") == "SPY"), None)
            assert spy_uni is not None, "SPY should be in universe"

            diag = client.get("/api/ui/symbol-diagnostics?symbol=SPY")
            assert diag.status_code == 200
            diag_body = diag.json()
            assert diag_body.get("composite_score") == spy_uni.get("score")
            assert diag_body.get("confidence_band") == spy_uni.get("band")
            assert diag_body.get("verdict") == spy_uni.get("verdict")
        finally:
            reset_output_dir()


class TestTruthTableGenerationSmoke:
    """Smoke: truth table generation helper (no real run)."""

    def test_truth_table_generation_smoke(self, tmp_path):
        """Generate TRUTH_TABLE_V2.md from a minimal fixture artifact dict."""
        sys.path.insert(0, str(_REPO))
        from scripts.market_live_validation import _generate_truth_table

        data = {
            "metadata": {
                "pipeline_timestamp": "2026-01-01T12:00:00Z",
                "market_phase": "OPEN",
                "universe_size": 2,
                "eligible_count": 0,
            },
            "symbols": [
                {
                    "symbol": "SPY",
                    "verdict": "HOLD",
                    "score": 50,
                    "band": "C",
                    "band_reason": "Band C because score >= 40 and < 60",
                    "primary_reason": "test",
                    "stage_status": "RUN",
                    "provider_status": "OK",
                },
            ],
        }
        out_path = tmp_path / "TRUTH_TABLE_V2.md"
        _generate_truth_table(data, out_path)
        assert out_path.exists()
        text = out_path.read_text(encoding="utf-8")
        assert "pipeline_timestamp" in text
        assert "SPY" in text
        assert "Band C" in text
